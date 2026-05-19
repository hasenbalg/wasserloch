# Simple Makefile for ESP8266 (ESP-12F) using arduino-cli
# Requirements:
#   arduino-cli core install esp8266:esp8266
#   arduino-cli lib install "ArduinoJson"

PORT ?= /dev/ttyACM0
FQBN ?= esp8266:esp8266:generic

all: compile

compile:
	./bin/arduino-cli compile --fqbn $(FQBN) .

upload:
	./bin/arduino-cli upload -p $(PORT) --fqbn $(FQBN) .

monitor:
	./bin/arduino-cli monitor -p $(PORT) -c baudrate=115200

clean:
	rm -rf build
