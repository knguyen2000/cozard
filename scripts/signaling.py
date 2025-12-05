#!/usr/bin/env python3
"""
WebRTC Signaling Server
Lightweight WebSocket server for SDP/ICE exchange between WebRTC peers
"""
import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONNECTED = set()

async def handler(websocket, path):
    """Handle WebSocket connections and broadcast messages"""
    peer_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
    logger.info(f"Peer connected: {peer_id}")
    CONNECTED.add(websocket)
    
    try:
        async for message in websocket:
            logger.info(f"Message from {peer_id}: {message[:100]}...")
            
            # Broadcast message to all other connected clients
            for conn in CONNECTED:
                if conn != websocket:
                    await conn.send(message)
                    logger.info(f"Forwarded to peer")
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Peer disconnected: {peer_id}")
    finally:
        CONNECTED.remove(websocket)

async def main():
    """Start signaling server"""
    server = await websockets.serve(handler, "0.0.0.0", 8443)
    logger.info("✓ Signaling server running on 0.0.0.0:8443")
    logger.info(f"  Waiting for WebRTC peers to connect...")
    
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
