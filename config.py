import os

SDN_HOST = os.getenv("SDN_HOST", "")
DDNG_HOST = os.getenv("DDNG_HOST", "")
TCP_PORT = os.getenv("TCP_PORT", 0)
READ_TIMEOUT= os.getenv("READ_TIMEOUT", 0.6)
RECONNECT_DELAY= os.getenv("RECONNECT_DELAY", 5.0)
MAX_RECONNECT_DELAY= os.getenv("MAX_RECONNECT_DELAY", 60) # Maximum delay between reconnection attempts
MAX_BUFFER= int(os.getenv("MAX_BUFFER", 1024))
SEND_RATE_LIMIT= os.getenv("SEND_RATE_LIMIT", 20)
KEEPALIVE_INTERVAL= os.getenv("KEEPALIVE_INTERVAL", 30) # Send keepalive every 30 seconds
KEEPALIVE_TIMEOUT= os.getenv("KEEPALIVE_TIMEOUT", 10.0) # Wait 10 seconds for keepalive response

SOMFY_ACK = os.getenv("SOMFY_ACK", False)

MQTT_HOST = os.getenv("MQTT_HOST", "192.168.0.253")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

MQTT_HOMEASSISTANT_PREFIX = os.getenv("MQTT_HOMEASSISTANT_PREFIX", "homeassistant")      
MQTT_BRIDGE_WILL =  os.getenv("MQTT_BRIDGE_WILL", "bridges/cover_somfy") 
MQTT_SOMFY_PREFIX = os.getenv("MQTT_SOMFY_PREFIX", "somfy")                                   

MQTT_DEBUG =  os.getenv("MQTT_DEBUG", False) 
SW_VER = os.getenv("SW_VER", "0.1a") 

LOG_LEVEL = os.getenv("LOG_LEVEL", "ERROR")

CONFIG_PORT = os.getenv("CONFIG_PORT", 4099)