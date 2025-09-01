from config import (
     MQTT_BRIDGE_WILL,  MQTT_HOMEASSISTANT_PREFIX
)
from somfy.helpers import print_address, to_string
from somfy.protocol import Message

device_id = {
            "device": {
                "identifiers": "somfybridge",
                "name": f"Somfy SDN MQTT  Bridge",
                "manufacturer": "Nerih82",
                "model": "Somfy SDN MQTT Bridge",
                "sw_version": f"1"
            }
        }

def sdn_discovery_payload():
    uid = "somfy_discovery_send"
    base_topic = f"{MQTT_HOMEASSISTANT_PREFIX}/button/{uid}"
    payload = {
        "platform": "button",
        "name": "Somfy Discovery",
        "unique_id": f"{uid}",
        "availability_topic": f"{MQTT_BRIDGE_WILL}/status",
        "retain": False,
        "icon": "mdi:find-replace",
        "command_topic" : f"{base_topic}/set",
        "device_class": "identify"
    }
    payload.update(device_id)
    return payload, f"{base_topic}/config"   # return config topic too, handy for publish

def sdn_cover_payload(msg : Message, strName=None):
    if not strName: 
        strName = print_address(msg.src)
        
    uid = f"somfy_{print_address(msg.src)}"
    
    model = msg.src_node_type_str
    
    base_topic = f"{MQTT_HOMEASSISTANT_PREFIX}/cover/{uid}"
    payload = ({
        "platform": "cover",
        "name": strName,
        "unique_id": f"{uid}",
        "availability_topic": f"{MQTT_BRIDGE_WILL}/status",
        "retain": False,
        "icon": "mdi:curtains",
        "command_topic": f"{base_topic}/set",
        "device_class":  "curtain",
    })
    payload.update(device_id)
    payload.update({
        "device": {
            "identifiers": [uid],   # or whatever string you want
            "name": strName,
            "model" : model
        }
    })
    return payload, f"{base_topic}/config"


def sdn_name_payload(msg : Message, strName=None):
    if not strName: 
        strName = print_address(msg.src)

    uid = f"somfy_btn_name_{print_address(msg.src)}"  
    base_topic = f"{MQTT_HOMEASSISTANT_PREFIX}/button/{uid}"
    model = msg.src_node_type_str

    payload = {
            "platform": "button",
            "name": "Get Name Label",
            "unique_id": f"{uid}",
            "availability_topic": f"{MQTT_BRIDGE_WILL}/status",
            "icon": "mdi:find-replace",
            "command_topic" : f"{base_topic}/set",
            "device_class": "identify"
        }
    payload.update(device_id)
    payload.update({
        "device": {
            "identifiers": f"somfy_{print_address(msg.src)}",   # or whatever string you want
            "name": strName,
            "model" : model
        }
    })
    return payload, f"{base_topic}/config"
