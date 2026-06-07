from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging
from backend.agents.graph import analysis_graph
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, ticker: str):
        await websocket.accept()
        if ticker not in self.active_connections:
            self.active_connections[ticker] = []
        self.active_connections[ticker].append(websocket)
        logger.info(f"WebSocket connected for ticker {ticker}. Total connections: {len(self.active_connections[ticker])}")

    def disconnect(self, websocket: WebSocket, ticker: str):
        if ticker in self.active_connections:
            if websocket in self.active_connections[ticker]:
                self.active_connections[ticker].remove(websocket)
                logger.info(f"WebSocket disconnected for ticker {ticker}. Remaining connections: {len(self.active_connections[ticker])}")
            if not self.active_connections[ticker]:
                del self.active_connections[ticker]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_to_ticker(self, message: str, ticker: str):
        if ticker in self.active_connections:
            disconnected = []
            for connection in self.active_connections[ticker]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to ticker {ticker}: {e}")
                    disconnected.append(connection)

            # Remove disconnected connections
            for conn in disconnected:
                self.disconnect(conn, ticker)


manager = ConnectionManager()


@router.websocket("/ws/analysis/{ticker}")
async def websocket_endpoint(websocket: WebSocket, ticker: str):
    """WebSocket endpoint for real-time analysis updates."""
    await manager.connect(websocket, ticker.upper())
    try:
        while True:
            # Keep connection alive and wait for client messages
            data = await websocket.receive_text()

            # If client sends a message, trigger analysis
            try:
                request_data = json.loads(data)
                if request_data.get("action") == "analyze":
                    # Run analysis in background and send updates
                    # For simplicity, we'll run the analysis and send result
                    # In a more complex implementation, we might send progress updates

                    # Initialize state for the graph
                    initial_state = {
                        "ticker": request_data.get("ticker", ticker).upper(),
                        "market_data": None,
                        "sector_data": None,
                        "stock_data": None,
                        "analysis_result": None,
                        "signal_output": None,
                        "confidence_breakdown": None,
                        "error": None,
                        "timestamp": None,
                        "retry_count": 0
                    }

                    # Run the analysis graph
                    final_state = await analysis_graph.ainvoke(initial_state)

                    # Prepare response
                    if final_state.get("error"):
                        response = {
                            "type": "error",
                            "message": final_state["error"]
                        }
                    else:
                        response = {
                            "type": "analysis_result",
                            "ticker": final_state["ticker"],
                            "signal": final_state.get("signal_output"),
                            "confidence_breakdown": final_state.get("confidence_breakdown"),
                            "analysis_details": final_state.get("analysis_result", {}),
                            "timestamp": final_state.get("timestamp")
                        }

                    await manager.send_personal_message(json.dumps(response), websocket)

            except json.JSONDecodeError:
                # Handle non-JSON messages (keep-alive pings, etc.)
                await manager.send_personal_message(json.dumps({"type": "ping_ack"}), websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, ticker)
        logger.info(f"WebSocket disconnected for {ticker}")
    except Exception as e:
        logger.error(f"WebSocket error for {ticker}: {e}")
        manager.disconnect(websocket, ticker)