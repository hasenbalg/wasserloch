#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <EEPROM.h>
#include <time.h>
#include <ArduinoJson.h>

#define EEPROM_SIZE 512

// Relay pins (adapt to your board)
const uint8_t RELAY_PINS[4] = {5, 4, 0, 2}; // D1, D2, D3, D4
static uint8_t lastOpenRelay = 0xFF;        // all closed. Enforced in setup function

ESP8266WebServer server(80);

// WiFi config
struct WifiConfig
{
  char ssid[32];
  char password[64];
  bool valid;
} wifiConfig;

// Schedule: up to 4 slots per day
// day: 0=Sunday..6=Saturday
// startMinutes: minutes from midnight
// durationMinutes
// relay: 0-3 relay
struct Slot
{
  uint16_t startMinutes;
  uint16_t durationMinutes;
  uint8_t relay;
};

const uint8_t MAX_SLOTS_PER_DAY = 4;
Slot schedule[7][MAX_SLOTS_PER_DAY];
uint8_t slotsCount[7];

// Time
bool timeSynced = false;

// ---------- Helpers ----------

void saveWifiConfig()
{
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.put(0, wifiConfig);
  EEPROM.commit();
}

void loadWifiConfig()
{
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.get(0, wifiConfig);
  if (strlen(wifiConfig.ssid) == 0)
  {
    wifiConfig.valid = false;
  }
}

void saveSchedule()
{
  EEPROM.begin(EEPROM_SIZE);
  int addr = sizeof(WifiConfig);
  EEPROM.put(addr, slotsCount);
  addr += sizeof(slotsCount);
  EEPROM.put(addr, schedule);
  EEPROM.commit();
}

void loadSchedule()
{
  EEPROM.begin(EEPROM_SIZE);
  int addr = sizeof(WifiConfig);
  EEPROM.get(addr, slotsCount);
  addr += sizeof(slotsCount);
  EEPROM.get(addr, schedule);
  // Basic sanity check
  for (int d = 0; d < 7; d++)
  {
    if (slotsCount[d] > MAX_SLOTS_PER_DAY)
      slotsCount[d] = 0;
  }
}

void startAP()
{
  WiFi.mode(WIFI_AP);
  WiFi.softAP("GardenWater", "water1234");
  Serial.println("Started AP: GardenWater / water1234");
}

bool connectWiFi()
{
  if (!wifiConfig.valid)
    return false;
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiConfig.ssid, wifiConfig.password);
  Serial.printf("Connecting to %s\n", wifiConfig.ssid);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000)
  {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.print("Connected, IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }
  return false;
}

void setupTimeNTP()
{
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println("Waiting for NTP time...");
  for (int i = 0; i < 10; i++)
  {
    time_t now = time(nullptr);
    if (now > 1600000000)
    { // ~2020
      timeSynced = true;
      Serial.println("Time synced via NTP");
      return;
    }
    delay(1000);
  }
  Serial.println("NTP failed, waiting for browser time...");
}

// ---------- HTTP Handlers ----------

void handleRoot()
{
  // Serve the Vue app (index.html)
  // For simplicity, we embed it here; you can also use SPIFFS.
  String html = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Garden Watering</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: sans-serif; margin: 1rem; }
    .day { border: 1px solid #ccc; padding: 0.5rem; margin-bottom: 0.5rem; }
    label { display:block; margin-top:0.25rem; }
    input, select { width: 100%; max-width: 200px; }
    .slots { margin-top:0.5rem; }
    .slot { border:1px solid #ddd; padding:0.25rem; margin:0.25rem 0; }
    .slot-overlap::before {
        content: "⚠ Overlaps with another slot";
        display: block;
        font-size: 0.85em;
        color: #d32f2f;
        margin-bottom: 0.25rem;
    }
    button { margin-top:0.5rem; }
  </style>
</head>
<body>
<div id="app">
  <h1>Garden Watering Scheduler</h1>

  <section>
    <h2>WiFi configuration</h2>
    <form @submit.prevent="saveWifi">
      <label>SSID
        <input v-model="wifi.ssid" required>
      </label>
      <label>Password
        <input v-model="wifi.password" type="password">
      </label>
      <button type="submit">Save WiFi & Reboot</button>
    </form>
  </section>

  <section>
    <h2>Time</h2>
    <p>Device time: {{ deviceTimeString }}</p>
    <button @click="sendBrowserTime">Sync from browser time</button>
  </section>

  <section>
    <h2>Schedule</h2>
    <div v-for="(day, dIndex) in days" :key="dIndex" class="day">
      <h3>{{ day }}</h3>
      <div class="slots">
        <div v-for="(slot, sIndex) in schedule[dIndex]" :key="sIndex" class="slot">
          <div>Start: {{ minutesToHHMM(slot.startMinutes) }},
               Duration: {{ slot.durationMinutes }} min,
               Relays: {{ relayToText(slot.relay) }}</div>
          <button @click="removeSlot(dIndex, sIndex)">Remove</button>
        </div>
      </div>
      <details>
        <summary>Add slot</summary>
        <label>Start time
          <input type="time" v-model="newSlot[dIndex].start">
        </label>
        <label>Duration (minutes)
          <input type="number" v-model.number="newSlot[dIndex].duration" min="1" max="600">
        </label>
        <label>Relay
          <select v-model.number="newSlot[dIndex].relay">
            <option v-for="r in 4" :value="r-1">Relay {{ r }}</option>
          </select>
        </label>
        <button @click="addSlot(dIndex)">Add</button>
      </details>
    </div>
    <button @click="saveSchedule">Save schedule</button>
  </section>
</div>

<script src="https://unpkg.com/vue@2.7.16/dist/vue.js"></script>
<script>
new Vue({
  el: '#app',
  data: {
    days: ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],
    wifi: { ssid: '', password: '' },
    schedule: [[],[],[],[],[],[],[]],
    newSlot: [],
    deviceTime: 0
  },
  created() {
    this.newSlot = this.days.map(() => ({ start: '06:00', duration: 10, relay: 0 }));
    this.fetchWifi();
    this.fetchSchedule();
    this.fetchTime();
    setInterval(this.fetchTime, 5000);
  },
  computed: {
    deviceTimeString() {
      if (!this.deviceTime) return 'unknown';
      const d = new Date(this.deviceTime * 1000);
      return d.toLocaleString();
    }
  },
  methods: {
    fetchWifi() {
      fetch('/api/wifi').then(r => r.json()).then(j => {
        this.wifi = j;
      }).catch(()=>{});
    },
    saveWifi() {
      fetch('/api/wifi', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(this.wifi)
      }).then(()=>{ alert('Saved. Device will reboot.'); });
    },
    fetchSchedule() {
      fetch('/api/schedule').then(r => r.json()).then(j => {
        this.schedule = j;
      }).catch(()=>{});
    },
    saveSchedule() {
      fetch('/api/schedule', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(this.schedule)
      }).then(()=>{ alert('Schedule saved'); });
    },
    minutesToHHMM(m) {
      const h = Math.floor(m/60);
      const mm = m%60;
      return ('0'+h).slice(-2)+':'+('0'+mm).slice(-2);
    },
    relayToText(relay) {
      return relay >= 0 && relay < 4 ? `Relay ${relay + 1}` : 'none';
    },
    /**
     * Returns true if slot at slotIndex overlaps any other slot
     * on the same day.
     */
    hasOverlap(dayIndex, slotIndex) {
      const target = this.schedule[dayIndex][slotIndex];
      if (!target) return false;
      const targetStart = target.startMinutes;
      const targetEnd   = target.startMinutes + target.durationMinutes;
      const day = this.schedule[dayIndex];
      for (let i = 0; i < day.length; i++) {
        if (i === slotIndex) continue;
        const other = day[i];
        const otherStart = other.startMinutes;
        const otherEnd   = other.startMinutes + other.durationMinutes;
        // Two intervals overlap iff one starts before the other ends
        if (targetStart < otherEnd && otherStart < targetEnd) {
          return true;
        }
      }
      return false;
    },
    /**
     * Add a new slot, but only if it doesn't overlap existing ones.
     */
    addSlot(dayIndex) {
        const ns = this.newSlot[dayIndex];
        const [hh, mm] = ns.start.split(':').map(Number);
        const startMinutes = hh * 60 + mm;
        const duration     = ns.duration;

        // Check against existing slots
        for (let i = 0; i < this.schedule[dayIndex].length; i++) {
            const existing = this.schedule[dayIndex][i];
            const existingEnd = existing.startMinutes + existing.durationMinutes;
            if (startMinutes < existingEnd && existing.startMinutes < startMinutes + duration) {
                alert(`Cannot add slot: overlaps with "${this.minutesToHHMM(existing.startMinutes)} – ${this.minutesToHHMM(existingEnd)}" (Relay ${existing.relay + 1})`);
              return;  // abort
            }
        }

        // Check against other new (unsaved) slots on same day
        for (let i = 0; i < this.schedule[dayIndex].length; i++) {
            const existing = this.schedule[dayIndex][i];
            // already checked above — new slots are only in the push below
        }

        this.schedule[dayIndex].push({
            startMinutes,
            durationMinutes: duration,
            relay: ns.relay
        });
    },
    removeSlot(dayIndex, slotIndex) {
      this.schedule[dayIndex].splice(slotIndex, 1);
    },
    fetchTime() {
      fetch('/api/time').then(r=>r.json()).then(j=>{
        this.deviceTime = j.epoch;
      }).catch(()=>{});
    },
    sendBrowserTime() {
      const epoch = Math.floor(Date.now()/1000);
      fetch('/api/time', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ epoch })
      }).then(()=>{ this.fetchTime(); });
    }
  }
});
</script>
</body>
</html>
)rawliteral";

  server.send(200, "text/html", html);
}

void handleGetWifi()
{
  DynamicJsonDocument doc(256);
  doc["ssid"] = wifiConfig.valid ? wifiConfig.ssid : "";
  doc["password"] = wifiConfig.valid ? wifiConfig.password : "";
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

void handlePostWifi()
{
  if (!server.hasArg("plain"))
  {
    server.send(400, "text/plain", "No body");
    return;
  }
  DynamicJsonDocument doc(256);
  DeserializationError err = deserializeJson(doc, server.arg("plain"));
  if (err)
  {
    server.send(400, "text/plain", "JSON error");
    return;
  }
  strlcpy(wifiConfig.ssid, doc["ssid"] | "", sizeof(wifiConfig.ssid));
  strlcpy(wifiConfig.password, doc["password"] | "", sizeof(wifiConfig.password));
  wifiConfig.valid = strlen(wifiConfig.ssid) > 0;
  saveWifiConfig();
  server.send(200, "text/plain", "OK, rebooting");
  delay(500);
  ESP.restart();
}

void handleGetSchedule()
{
  DynamicJsonDocument doc(4096);
  JsonArray days = doc.to<JsonArray>();
  for (int d = 0; d < 7; d++)
  {
    JsonArray dayArr = days.createNestedArray();
    for (int i = 0; i < slotsCount[d]; i++)
    {
      JsonObject o = dayArr.createNestedObject();
      o["startMinutes"] = schedule[d][i].startMinutes;
      o["durationMinutes"] = schedule[d][i].durationMinutes;
      o["relay"] = schedule[d][i].relay;
    }
  }
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

bool hasOverlap(int day, const Slot *slots, uint8_t count) {
    for (int i = 0; i < count; i++) {
        uint16_t startA = slots[i].startMinutes;
        uint16_t endA   = startA + slots[i].durationMinutes;
        for (int j = i + 1; j < count; j++) {
            uint16_t startB = slots[j].startMinutes;
            uint16_t endB   = startB + slots[j].durationMinutes;
            if (startA < endB && startB < endA) return true;
        }
    }
    return false;
}

void handlePostSchedule()
{
  if (!server.hasArg("plain"))
  {
    server.send(400, "text/plain", "No body");
    return;
  }

  DynamicJsonDocument doc(4096);
  DeserializationError err = deserializeJson(doc, server.arg("plain"));
  if (err || !doc.is<JsonArray>())
  {
    server.send(400, "text/plain", "JSON error");
    return;
  }

  JsonArray days = doc.as<JsonArray>();
  for (int d = 0; d < 7 && d < (int)days.size(); d++)
  {
    JsonArray dayArr = days[d].as<JsonArray>();
    uint8_t count = 0;
    for (JsonObject o : dayArr)
    {
      if (count >= MAX_SLOTS_PER_DAY)
        break;
      schedule[d][count].startMinutes = o["startMinutes"] | 0;
      schedule[d][count].durationMinutes = o["durationMinutes"] | 0;
      schedule[d][count].relay = o["relay"] | 0;
      count++;
    }
    slotsCount[d] = count;
  }

  // Reject if any day has overlapping slots
  for (int d = 0; d < 7; d++)
  {
    if (hasOverlap(d, schedule[d], slotsCount[d]))
    {
      server.send(409, "text/plain", "Overlapping slots detected");
      return;
    }
  }

  saveSchedule();
  server.send(200, "text/plain", "OK");
}

void handleGetTime()
{
  time_t now = time(nullptr);
  DynamicJsonDocument doc(64);
  doc["epoch"] = (uint32_t)now;
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

void handlePostTime()
{
  if (!server.hasArg("plain"))
  {
    server.send(400, "text/plain", "No body");
    return;
  }
  DynamicJsonDocument doc(128);
  if (deserializeJson(doc, server.arg("plain")))
  {
    server.send(400, "text/plain", "JSON error");
    return;
  }
  uint32_t epoch = doc["epoch"] | 0;
  struct timeval tv;
  tv.tv_sec = epoch;
  tv.tv_usec = 0;
  settimeofday(&tv, nullptr);
  timeSynced = true;
  server.send(200, "text/plain", "Time set");
}

// ---------- Scheduler ----------

void updateRelays()
{
  time_t now = time(nullptr);
  if (now < 100000)
    return; // invalid time

  struct tm *tmNow = localtime(&now);
  int wday = tmNow->tm_wday; // 0=Sunday
  int minutes = tmNow->tm_hour * 60 + tmNow->tm_min;

  uint8_t activeRelay = 0;

  for (int i = 0; i < slotsCount[wday]; i++)
  {
    Slot &s = schedule[wday][i];
    if (minutes >= s.startMinutes &&
        minutes < s.startMinutes + s.durationMinutes)
    {
      activeRelay |= (1 << s.relay);
    }
  }
  if (activeRelay == lastOpenRelay)
    return; // no change
  lastOpenRelay = activeRelay;

  for (int r = 0; r < 4; r++)
  {
    bool on = (activeRelay & (1 << r));
    digitalWrite(RELAY_PINS[r], on ? LOW : HIGH);
  }
}

// ---------- Setup & Loop ----------

void setup()
{
  Serial.begin(115200);
  delay(100);

  for (int i = 0; i < 4; i++)
  {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], HIGH); // off
  }

  loadWifiConfig();
  loadSchedule();

  bool wifiOk = connectWiFi();
  if (!wifiOk)
  {
    startAP();
  }
  else
  {
    setupTimeNTP();
  }

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/wifi", HTTP_GET, handleGetWifi);
  server.on("/api/wifi", HTTP_POST, handlePostWifi);
  server.on("/api/schedule", HTTP_GET, handleGetSchedule);
  server.on("/api/schedule", HTTP_POST, handlePostSchedule);
  server.on("/api/time", HTTP_GET, handleGetTime);
  server.on("/api/time", HTTP_POST, handlePostTime);

  server.begin();
  Serial.println("HTTP server started");
}

unsigned long lastRelayUpdate = 0;

void loop()
{
  server.handleClient();

  if (millis() - lastRelayUpdate > 1000)
  {
    lastRelayUpdate = millis();
    updateRelays();
  }
}
