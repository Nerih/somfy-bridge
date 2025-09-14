#!/usr/bin/env python3
"""
Hardened Dual Serial SDN Bridge with Queued Forwarding, Reconnects, and Emoji Logging
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, List
from queue import Queue
from somfy.helpers import is_unicast_non_group
from somfy.protocol import *
import somfy.messages  # Auto-register message
import sys
import signal

from config import (
     ACK_MAX_RETRIES, ACK_RETRY_INTERVAL, MQTT_SOMFY_PREFIX, MQTT_BRIDGE_WILL,LOG_LEVEL,SDN_HOST,DDNG_HOST,TCP_PORT,
     READ_TIMEOUT,RECONNECT_DELAY,MAX_RECONNECT_DELAY,MAX_BUFFER,SEND_RATE_LIMIT,KEEPALIVE_INTERVAL,
     KEEPALIVE_TIMEOUT
)

# ───────────────────────────────────────────────
# Logging setup
# ───────────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s.%(msecs)03d %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("🔌 SDNBridge")

PORTS = {
    SDN_HOST: "SDN",
    DDNG_HOST: "DDNG"
}


class AsyncConnection:
    def __init__(self, ip: str, label: str):
        self.ip = ip
        self.label = label
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.buffer = bytearray()
        self._stop = False
        self._connected = asyncio.Event()
        self.send_queue = asyncio.Queue()
        self.label = label
        self.last_activity = datetime.now()
        self.reconnect_attempts = 0
        self.current_delay = RECONNECT_DELAY

    async def connect_loop(self):
        while not self._stop:
            try:
                logger.info(f"🔄 {self.label} attempting connection to {self.ip}:{TCP_PORT} (attempt #{self.reconnect_attempts + 1})")
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, TCP_PORT),
                    timeout=10.0
                )
                self._connected.set()
                self.last_activity = datetime.now()
                self.reconnect_attempts = 0
                self.current_delay = RECONNECT_DELAY
                logger.info(f"✅ {self.label} connected to {self.ip}:{TCP_PORT}")

                tasks = [
                    asyncio.create_task(self.listen_loop()),
                    asyncio.create_task(self.send_loop()),
                    asyncio.create_task(self.keepalive_loop())
                ]

                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

                logger.info(f"🔌 {self.label} connection tasks completed, triggering reconnection")

                for i, task in enumerate(done):
                    if task.exception():
                        logger.warning(f"❌ {self.label} task {i} failed: {task.exception()}")

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.debug(f"🛑 {self.label} task cancelled")

            except asyncio.TimeoutError:
                logger.warning(f"⏰ {self.label} connection timeout to {self.ip}:{TCP_PORT}")
            except Exception as e:
                logger.warning(f"❌ {self.label} connection failed: {e}")
            finally:
                self._connected.clear()
                if self.writer:
                    self.writer.close()
                    await self.writer.wait_closed()
                self.reader = self.writer = None

                self.reconnect_attempts += 1
                if self.reconnect_attempts > 1:
                    self.current_delay = min(self.current_delay * 1.5, MAX_RECONNECT_DELAY)

                logger.info(f"🔄 {self.label} reconnecting in {self.current_delay:.1f}s... (attempt #{self.reconnect_attempts})")
                await asyncio.sleep(self.current_delay)


    async def listen_loop(self):
        try:
            while not self._stop:
                try:
                    # Add timeout to read operation
                    chunk = await asyncio.wait_for(
                        self.reader.read(1024), 
                        timeout=READ_TIMEOUT
                    )
                    if not chunk:
                        logger.warning(f"🔌 {self.label} connection closed by peer")
                        raise ConnectionError("Connection closed by peer")
                    
                    self.buffer += chunk
                    self.last_activity = datetime.now()
                    logger.debug(f"← {self.label} Raw: {chunk.hex().upper()}")
                    await self.parse_buffer()
                    
                except asyncio.TimeoutError:
                    #disabled, as we don't need a timeout, if there is a socket drop
                    #the application shoudl terminat, and restart as per docker rules
                    # Check if we've been idle too long
                    #idle_time = (datetime.now() - self.last_activity).total_seconds()
                    #if idle_time > KEEPALIVE_INTERVAL + KEEPALIVE_TIMEOUT:
                    #    logger.warning(f"⏰ {self.label} connection appears dead (idle {idle_time:.1f}s)")
                    #    raise ConnectionError(f"Connection idle for {idle_time:.1f}s")
                    # Otherwise, timeout is normal - continue listening
                    continue
                    
                except asyncio.IncompleteReadError:
                    logger.warning(f"⚠️ {self.label} Incomplete read - connection broken")
                    raise ConnectionError("Incomplete read - connection broken")
                except asyncio.CancelledError:
                    logger.info(f"🛑 {self.label} listen task cancelled")
                    raise
                except Exception as e:
                    logger.exception(f"❌ {self.label} read error: {e}")
                    raise ConnectionError(f"Read error: {e}")
        finally:
            logger.info(f"📴 {self.label} listener shut down")

    async def keepalive_loop(self):
        """Send periodic keepalive messages and detect dead connections"""
        try:
            while not self._stop:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                
                # Check if connection is still alive by trying to write
                if self.writer and not self.writer.is_closing():
                    try:
                        # Send a small keepalive packet (you might want to use a proper keepalive message)
                        self.writer.write(b'')  # Simple keepalive byte
                        await asyncio.wait_for(self.writer.drain(), timeout=KEEPALIVE_TIMEOUT)
                        logger.debug(f"💓 {self.label} keepalive sent")
                    except Exception as e:
                        logger.warning(f"💔 {self.label} keepalive failed: {e}")
                        raise ConnectionError(f"Keepalive failed: {e}")
                else:
                    raise ConnectionError("Connection closed")
        except asyncio.CancelledError:
            logger.debug(f"🛑 {self.label} keepalive cancelled")
            raise
        except Exception as e:
            logger.warning(f"❌ {self.label} keepalive error: {e}")
            raise

    async def send_loop(self):
        try:
            while not self._stop:
                try:
                    data = await self.send_queue.get()
                    if self.writer and not self.writer.is_closing():
                        self.writer.write(data)
                        await asyncio.wait_for(self.writer.drain(), timeout=5.0)
                        await asyncio.sleep(1 / SEND_RATE_LIMIT)
                    else:
                        logger.warning(f"❌ {self.label} cannot send - connection closed")
                        raise ConnectionError("Connection closed")
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ {self.label} send timeout")
                    raise ConnectionError("Send timeout")
                except Exception as e:
                    logger.warning(f"❌ {self.label} send error: {e}")
                    raise ConnectionError(f"Send error: {e}")
        except asyncio.CancelledError:
            logger.info(f"🛑 {self.label} send task cancelled")
            raise

    async def parse_buffer(self):
        while self.buffer:
            try:
                msg, offset = Message.parse_from_bytes(self.buffer)
                if msg:
                    raw = self.buffer[:offset]
                    logger.debug(f"✉️  {self.label} Bytes: {raw.hex().upper()}")
                    logger.info(f"✅ {self.label}:{msg}")
                    self.buffer = self.buffer[offset:]
                    # Forwarding will be handled outside
                    await Bridge.instance.forward_message(msg, self.label)
                else:
                    if len(self.buffer) < 11:
                        break
                    self.buffer.pop(0)
            except Exception as e:
                logger.warning(f"⚠️ {self.label} parse error: {e}")
                self.buffer.pop(0)

    def send(self, msg: Message):
        if not self._connected.is_set():
            logger.warning(f"⚠️ {self.label} not connected - dropping message (will retry when reconnected)")
            return
        
        raw = msg.to_bytes()
        try:
            self.send_queue.put_nowait(raw)
            logger.debug(f"➡️  {self.label} Queued send: {msg}")
        except asyncio.QueueFull:
            logger.warning(f"⚠️ {self.label} send queue full - dropping message")

    async def wait_for_connection(self, timeout: float = 30.0):
        """Wait for connection to be established"""
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def stop(self):
        self._stop = True


class Bridge:
    instance = None

    def __init__(self):
        Bridge.instance = self
        self.connections = {}
        self.pending_acks = {}   # message_id -> asyncio.Event

    async def start(self):
        tasks = []
        for ip, label in PORTS.items():
            conn = AsyncConnection(ip, label)
            self.connections[label] = conn
            tasks.append(conn.connect_loop())
        await asyncio.gather(*tasks)

    async def stop(self):
        for conn in self.connections.values():
            conn.stop()

    async def forward_message(self, msg: Message, source_label: str):
        # ---------- Helpers ----------
        def _key_for_ackish(m: Message):
            # ACK/NACK swap src/dest vs the original outgoing
            return (tuple(getattr(m, "dest", []) or []),
                    tuple(getattr(m, "src", []) or []))

        from somfy.messages import Ack, Nack, UnknownMessage

        # ---------- ACK / NACK handling ----------
        if isinstance(msg, (Ack, Nack)):
            key = _key_for_ackish(msg)
            event = self.pending_acks.get(key)
            if event:
                event.set()
                self.pending_acks.pop(key, None)
                if isinstance(msg, Ack):
                    logger.info(f"🟢 ACK matched pending send {key}")
                else:
                    logger.warning(f"🟠 NACK matched pending send {key}")
            else:
                tag = "ACK" if isinstance(msg, Ack) else "NACK"
                logger.debug(f"ℹ️ {tag} with no pending match: src={getattr(msg,'src',None)} dest={getattr(msg,'dest',None)}")
            return  # do not forward ACK/NACK

        # ---------- Non-ACK path ----------
        if isinstance(msg, UnknownMessage):
            logger.warning(f"⚠️ {source_label} Skipping unknown message: {msg}")
            return

        # Remap per your rules
        msg = self.remap_node_type(msg, source_label)

        # Route selection (your original logic)
        dest = getattr(msg, "dest", None)
        if source_label == "SDN" and dest == [0xFF, 0xFF, 0xF0]:
            target_label = "DDNG"
        else:
            target_label = "SDN" if source_label == "DDNG" else "DDNG"

        target_conn = self.connections.get(target_label)
        if not target_conn:
            logger.warning(f"❌ No connection for target {target_label}; dropping {msg}")
            return

        # Reliable send iff ack_requested
        if getattr(msg, "ack_requested", False):
            ok = await self.send_with_ack(target_conn, msg)
            if not ok:
                logger.error(f"❌ Failed to get ACK for {(tuple(msg.src), tuple(msg.dest))}")
        else:
            target_conn.send(msg)


    async def send_with_ack(self, conn: AsyncConnection, msg: Message):
        """
        Retry send until ACK/NACK observed or attempts exhausted.
        Keys pending_acks by (src_tuple, dest_tuple) to match forward_message().
        """
        key = (tuple(msg.src), tuple(msg.dest))

        # Register (or reuse) the event before first transmit
        event = self.pending_acks.get(key)
        if event is None:
            event = asyncio.Event()
            self.pending_acks[key] = event

        try:
            for attempt in range(ACK_MAX_RETRIES):
                conn.send(msg)
                try:
                    await asyncio.wait_for(event.wait(), timeout=ACK_RETRY_INTERVAL)
                    logger.info(f"✅ ACK/NACK seen for {key} after {attempt+1} attempt(s)")
                    return True
                except asyncio.TimeoutError:
                    logger.debug(f"⏰ No ACK yet for {key}, retry {attempt+1}/{ACK_MAX_RETRIES}")
            logger.error(f"❌ No ACK after {ACK_MAX_RETRIES} attempts for {key}")
            return False
        finally:
            # Clean up regardless of success/failure to avoid leaks
            self.pending_acks.pop(key, None)


            def remap_node_type(self, msg: Message, label: str):
                try:
                    # DDNG → SDN: remap node type 2 → 0
                    if label == "DDNG" and msg.des_node_type == 2:
                        msg.des_node_type = 0

                        # Only request ACK (to trigger reliable send step 5) for non-group/unicast
                        if is_unicast_non_group(msg.dest):
                            msg.ack_requested = True
                            logger.debug(f"🔁 Remap DDNG→SDN: unicast {msg.dest} → ACK ON")
                        else:
                            # Ensure we don't force ACKs on group/broadcast
                            msg.ack_requested = False
                            logger.debug(f"🔁 Remap DDNG→SDN: group/broadcast {msg.dest} → ACK OFF")

                    # SDN → DDNG: preserve your existing mapping; no forced ACK here
                    elif label == "SDN" and msg.dest == [0xFF, 0xFF, 0xF0]:
                        msg.src_node_type = 2
                        # Leave msg.ack_requested as-is (don’t force ACKs for broadcast)
                except Exception as e:
                    logger.error(f"⚠️ Remap error: {e}")
                return msg


async def main():
    bridge = Bridge()
    try:
        await bridge.start()
    except KeyboardInterrupt:
        print("🛑 Caught Ctrl+C, stopping...")
        await bridge.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Program exited cleanly via Ctrl+C")