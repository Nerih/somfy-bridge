import os
MQTT_HOST = os.getenv("MQTT_HOST", "192.168.0.253")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

MQTT_HOMEASSISTANT_PREFIX = os.getenv("MQTT_HOMEASSISTANT_PREFIX", "homeassistant")      
MQTT_BRIDGE_WILL =  os.getenv("MQTT_BRIDGE_WILL", "bridges/cover_somfy") 
MQTT_SOMFY_PREFIX = os.getenv("MQTT_SOMFY_PREFIX", "somfy")                                   

MQTT_DEBUG =  os.getenv("MQTT_DEBUG", False) 
SW_VER = os.getenv("SW_VER", "0.1a") 
