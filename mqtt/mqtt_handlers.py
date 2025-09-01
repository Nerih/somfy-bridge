import json
# --- add near other globals ---
import asyncio

_discovery_task: asyncio.Task | None = None
_discovery_lock = asyncio.Lock()
_DISCOVERY_SECONDS = 60
_DISCOVERY_INTERVAL = 10
_DISCOVERY_BURSTS = _DISCOVERY_SECONDS // _DISCOVERY_INTERVAL  # 6


from mqtt.publisher import MQTTPublisher

from config import (
    MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
     MQTT_BRIDGE_WILL, MQTT_DEBUG, MQTT_HOMEASSISTANT_PREFIX
)

from mqtt.discovery import sdn_discovery_payload

import somfy.messages as sdn_msgs  # classes auto-registered

import logging
logger = logging.getLogger("somfy_sdn")

__schedule = None          # scheduler(coro_fn, *args, **kwargs)
__send_to_sdn = None       # send_to_sdn(Message)
__mqtt_publish = None      # mqtt_publish(topic, payload, retain)

def set_asyncio_scheduler(scheduler_callable):
    global __schedule
    __schedule = scheduler_callable

def set_send_to_sdn(fn):
    global __send_to_sdn
    __send_to_sdn = fn

def set_mqtt_publish_fn(fn):
    global __mqtt_publish
    __mqtt_publish = fn


mqtt_client = None


def handle_mqtt_connect(client, userdata, flags, rc):
    if rc != 0:
        logging.error(f"❌ Connection failed with code {rc}")
        return

    try:
        client.subscribe(f"{MQTT_HOMEASSISTANT_PREFIX}/cover/+/+/set")
        logging.info(f"📡 Subscribed to {MQTT_HOMEASSISTANT_PREFIX}/cover/+/+/set")
        
        payload, config_topic = sdn_discovery_payload()
        mqtt_client.publish(config_topic, json.dumps(payload), retain=True)
        logging.info(f"📡 Published SDN Button discovery → {payload['name']}")
        
        client.subscribe(f"{MQTT_HOMEASSISTANT_PREFIX}/button/+/set")
        logging.info(f"📡 Subscribed to {MQTT_HOMEASSISTANT_PREFIX}/button/+/set")

    except Exception as e:
        logging.error(f"❌ Failed to subscribe: {e}")


# --- tiny tweak in mqtt_on_msg so reschedules cleanly and quietly if already running ---
def mqtt_on_msg(topic, payload):
    if topic == f"{MQTT_HOMEASSISTANT_PREFIX}/button/somfy_discovery_send/set":
        logger.info("🔔 MQTT: Somfy Discovery button pressed")
        if __schedule:
            __schedule(run_sdn_discovery)
        else:
            logger.error("No scheduler set")
        return

    if topic.startswith(f"{MQTT_HOMEASSISTANT_PREFIX}/button/somfy_btn_name_") and topic.endswith("/set"):
        if __schedule:
            __schedule(run_sdn_getNodeLabel, topic)
        else:
            logger.error("No scheduler set")
        return

    logging.info(f"!! Unhandled:{topic}")

    

    logging.info(f"!! Unhandled:{topic}")

    #elif topic == MQTT_DYNALITE_PREFIX:
    #    try:
    #        parsed = json.loads(payload)
    #        handle_dynet_packet(parsed, dynalite_map,mqtt_client)
    #    except Exception as e:
    #        log(f"❌ Invalid Dynalite JSON: {e}")
    #elif topic.startswith(f"{MQTT_DYNALITE_PREFIX}/set/res/"):
    #    handle_response_ack(topic, payload,pending_responses,mqtt_client)
    #elif topic == MQTT_DYNALITE_WILL:
    #    bridge_online["dynalite"] = payload.lower() == "online"

def start_mqtt():
    global mqtt_client
    mqtt_client = MQTTPublisher(
        mqtt_username=MQTT_USERNAME,
        mqtt_password=MQTT_PASSWORD,
        mqtt_host=MQTT_HOST,
        mqtt_port=MQTT_PORT,
        will_topic=f"{MQTT_BRIDGE_WILL}/status",
        mqtt_debug=MQTT_DEBUG
    )
    mqtt_client.on_connect = handle_mqtt_connect
    mqtt_client.on_message = mqtt_on_msg
    return mqtt_client



# --- replace your run_sdn_discovery with this guarded version ---
async def run_sdn_discovery():
    """
    Fire-and-forget SDN discovery. If one is already running, exit quietly.
    Sends GetNodeAddr immediately and then every 10s for the next 60s (total 6 sends).
    """
    global _discovery_task

    # ensure only one runner at a time
    async with _discovery_lock:
        if _discovery_task and not _discovery_task.done():
            logger.info("ℹ️ Discovery already running; ignoring new request")
            return

        # create and track a background task
        loop = asyncio.get_running_loop()
        _discovery_task = loop.create_task(_run_sdn_discovery_worker())
        _discovery_task.add_done_callback(lambda t: logger.info("✅ Discovery finished") if not t.cancelled() else logger.info("⏹️ Discovery cancelled"))
        logger.info("▶️ Discovery started")


# --- add the worker that does the repeated sends ---
async def _run_sdn_discovery_worker():
    try:
        from somfy.messages import GetNodeAddr
        from somfy.messages import SetNodeDiscovery

        # prepare fixed message template once
        base = GetNodeAddr()
        base.src_node_type = 0
        base.src = [0xFF, 0xFF, 0xF1]
        base.dest = [0xFF,0XFF, 0XFF]
        base.ack_requested = False

        # send now + every 10s for 60s (6 total)
        sends = _DISCOVERY_BURSTS
        for i in range(sends):
            # clone per send in case the class mutates internals on transmit
            msg = SetNodeDiscovery()
            msg.src_node_type = base.src_node_type
            msg.src = base.src[:]
            msg.ack_requested = base.ack_requested
            msg.dest = base.dest[:]
            #raw = msg.to_bytes()
            #print(f"TX → {raw.hex(' ').upper()}")   # nice readable hex dump
            try:
                __send_to_sdn(msg)
                logger.info(f"📤 SDN discovery sent ({i+1}/{sends}) SetNodeDiscovery")
                try:
                    msg = GetNodeAddr()
                    msg.src_node_type = base.src_node_type
                    msg.src = base.src[:]
                    msg.ack_requested = base.ack_requested
                    msg.dest = base.dest[:]
                    __send_to_sdn(msg)
                    logger.info(f"📤 SDN discovery sent ({i+1}/{sends}) GetNodeAddr")
                except Exception as tx_err:
                    logger.error(f"❌ discovery send failed ({i+1}/{sends}): {tx_err}")                
            
            except Exception as tx_err:
                logger.error(f"❌ discovery send failed ({i+1}/{sends}): {tx_err}")

            if i < sends - 1:
                await asyncio.sleep(_DISCOVERY_INTERVAL)

    except asyncio.CancelledError:
        # allow graceful cancellation
        raise
    except Exception as e:
        logger.error(f"❌ discovery worker crashed: {e}")


async def run_sdn_getNodeLabel(topic):

    try:      

        from somfy.messages import GetNodeLabel
        #from topic extract nodeid
        msg = GetNodeLabel()
        msg.src_node_type = 5
        msg.src = [0xFF, 0xFF, 0xF1]

        nid = topic.split("/")[2].rsplit("_", 1)[-1].strip()
        addr = int(nid, 16) if all(c in "0123456789ABCDEFabcdef" for c in nid) else int(nid)
        msg.dest = [(addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF]
        
        msg.ack_requested = False
        #raw = msg.to_bytes()
        #print(f"TX → {raw.hex(' ').upper()}")   # nice readable hex dump
        __send_to_sdn(msg)
        logger.info(f"📤 SDN getNodeLabel sent {msg}")
    except Exception as e:
        logger.error(f"❌ getNodeLabel failed: {e}")
