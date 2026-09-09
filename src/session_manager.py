import time
from typing import Dict, Any, Optional, List
from collections import OrderedDict

from src.config import SESSION_TIMEOUT_MIN


class SessionManager:
    def __init__(self):
        self._sessions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._max_history = 3

    def _cleanup_expired(self):
        now = time.time()
        expired = []
        for sid, sess in self._sessions.items():
            if now - sess.get("last_active", 0) > SESSION_TIMEOUT_MIN * 60:
                expired.append(sid)
        for sid in expired:
            del self._sessions[sid]

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        self._cleanup_expired()
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "created_at": time.time(),
                "last_active": time.time(),
                "history": [],
                "context": {}
            }
        self._sessions[session_id]["last_active"] = time.time()
        self._sessions.move_to_end(session_id)
        return self._sessions[session_id]

    def add_history(self, session_id: str, message: str, intent: str,
                    params: Dict[str, Any], reply: str = ""):
        session = self.get_or_create(session_id)
        session["history"].append({
            "message": message,
            "intent": intent,
            "params": params,
            "reply": reply,
            "time": time.time()
        })
        if len(session["history"]) > self._max_history:
            session["history"] = session["history"][-self._max_history:]
        self._inherit_context(session, params)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """返回最近 N 轮对话历史(含 reply)"""
        session = self.get_or_create(session_id)
        return session.get("history", []).copy()

    def _inherit_context(self, session: Dict[str, Any], current_params: Dict[str, Any]):
        ctx = session.get("context", {})
        if "year" in current_params:
            ctx["year"] = current_params["year"]
        if "month" in current_params:
            ctx["month"] = current_params["month"]
        if "dimension" in current_params:
            ctx["dimension"] = current_params["dimension"]
        if "category" in current_params:
            ctx["category"] = current_params["category"]
        if "street" in current_params:
            ctx["street"] = current_params["street"]
        session["context"] = ctx

    def get_context(self, session_id: str) -> Dict[str, Any]:
        session = self.get_or_create(session_id)
        return session.get("context", {}).copy()

    def clear(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]


session_manager = SessionManager()
