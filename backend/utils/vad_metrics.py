"""
VAD Metrics Tracker - Backend Component

Tracks:
- Interruption events from Gemini Live API
- Tool call cancellations
- Audio streaming interruptions
- Timing metrics for cancel acknowledgment

NO PII - Only timing and operational metrics
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import structlog


@dataclass
class InterruptionEvent:
    """Record of a single interruption event"""
    timestamp: float  # time.time()
    perf_timestamp: float  # time.perf_counter() for precise timing
    canceled_tool_call_ids: List[str] = field(default_factory=list)
    audio_frames_discarded: int = 0
    acknowledgment_sent_at: Optional[float] = None  # time.perf_counter()
    ack_latency_ms: Optional[float] = None


@dataclass
class ToolCallEvent:
    """Record of a tool call (for correlation with interruptions)"""
    timestamp: float
    perf_timestamp: float
    tool_name: str
    call_id: str
    was_canceled: bool = False
    interruption_id: Optional[str] = None  # Links to interruption that canceled it


class VADMetrics:
    """
    Metrics tracker for VAD tuning and barge-in performance.
    
    Focuses on backend-observable events:
    - Gemini interruption notifications
    - Tool call cancellations
    - Timing for interruption handling
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.session_start = time.time()
        self.interruptions: List[InterruptionEvent] = []
        self.tool_calls: List[ToolCallEvent] = []
        self.log = structlog.get_logger().bind(
            component="VADMetrics",
            session_id=session_id
        )
        
        self.log.info("vad_metrics_initialized")
    
    def record_interruption(
        self, 
        canceled_call_ids: Optional[List[str]] = None,
        audio_frames_discarded: int = 0
    ) -> InterruptionEvent:
        """
        Record an interruption event from Gemini.
        
        Args:
            canceled_call_ids: IDs of tool calls that were canceled
            audio_frames_discarded: Number of queued audio frames that were discarded
        
        Returns:
            The created InterruptionEvent
        """
        event = InterruptionEvent(
            timestamp=time.time(),
            perf_timestamp=time.perf_counter(),
            canceled_tool_call_ids=canceled_call_ids or [],
            audio_frames_discarded=audio_frames_discarded
        )
        
        self.interruptions.append(event)
        
        self.log.info(
            "interruption_detected",
            canceled_calls=len(event.canceled_tool_call_ids),
            call_ids=[cid[:8] for cid in event.canceled_tool_call_ids],
            audio_frames_discarded=audio_frames_discarded
        )
        
        # Mark tool calls as canceled
        for call_id in event.canceled_tool_call_ids:
            for tool_call in self.tool_calls:
                if tool_call.call_id == call_id and not tool_call.was_canceled:
                    tool_call.was_canceled = True
                    tool_call.interruption_id = str(len(self.interruptions) - 1)
        
        return event
    
    def record_interruption_ack_sent(self, event: InterruptionEvent) -> None:
        """
        Record when we sent interruption acknowledgment to frontend.
        
        Args:
            event: The interruption event to update
        """
        now = time.perf_counter()
        event.acknowledgment_sent_at = now
        event.ack_latency_ms = (now - event.perf_timestamp) * 1000
        
        self.log.info(
            "interruption_ack_sent",
            ack_latency_ms=round(event.ack_latency_ms, 1),
            meets_target=event.ack_latency_ms < 150
        )
    
    def record_tool_call(self, tool_name: str, call_id: str) -> None:
        """
        Record a tool call event.
        
        Args:
            tool_name: Name of the tool being called
            call_id: Unique ID of the tool call
        """
        event = ToolCallEvent(
            timestamp=time.time(),
            perf_timestamp=time.perf_counter(),
            tool_name=tool_name,
            call_id=call_id
        )
        
        self.tool_calls.append(event)
        
        self.log.debug(
            "tool_call_recorded",
            tool_name=tool_name,
            call_id=call_id[:8]
        )
    
    def get_statistics(self) -> Dict[str, any]:
        """
        Calculate summary statistics.
        
        Returns:
            Dictionary of metrics
        """
        total_interruptions = len(self.interruptions)
        total_tool_calls = len(self.tool_calls)
        canceled_tool_calls = sum(1 for tc in self.tool_calls if tc.was_canceled)
        
        ack_latencies = [
            event.ack_latency_ms 
            for event in self.interruptions 
            if event.ack_latency_ms is not None
        ]
        
        avg_ack_latency = sum(ack_latencies) / len(ack_latencies) if ack_latencies else 0
        
        # P95 latency
        if ack_latencies:
            sorted_latencies = sorted(ack_latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p95_ack_latency = sorted_latencies[p95_idx]
        else:
            p95_ack_latency = 0
        
        total_audio_frames_discarded = sum(
            event.audio_frames_discarded 
            for event in self.interruptions
        )
        
        return {
            "session_id": self.session_id,
            "session_duration_s": time.time() - self.session_start,
            "total_interruptions": total_interruptions,
            "total_tool_calls": total_tool_calls,
            "canceled_tool_calls": canceled_tool_calls,
            "cancellation_rate_pct": (
                (canceled_tool_calls / total_tool_calls * 100) 
                if total_tool_calls > 0 
                else 0
            ),
            "avg_ack_latency_ms": round(avg_ack_latency, 1),
            "p95_ack_latency_ms": round(p95_ack_latency, 1),
            "ack_latency_target_met": p95_ack_latency < 150 if p95_ack_latency > 0 else None,
            "total_audio_frames_discarded": total_audio_frames_discarded,
        }
    
    def print_summary(self) -> None:
        """Print a formatted summary of metrics."""
        stats = self.get_statistics()
        
        self.log.info("=" * 60)
        self.log.info("VAD METRICS SUMMARY (Backend)")
        self.log.info("=" * 60)
        self.log.info(f"Session ID: {stats['session_id']}")
        self.log.info(f"Duration: {stats['session_duration_s']:.1f}s")
        self.log.info("")
        self.log.info("INTERRUPTIONS:")
        self.log.info(f"  Total: {stats['total_interruptions']}")
        self.log.info(f"  Avg Ack Latency: {stats['avg_ack_latency_ms']:.1f}ms")
        self.log.info(f"  P95 Ack Latency: {stats['p95_ack_latency_ms']:.1f}ms")
        if stats['ack_latency_target_met'] is not None:
            status = "✅ TARGET MET" if stats['ack_latency_target_met'] else "❌ EXCEEDS TARGET"
            self.log.info(f"  Target (<150ms): {status}")
        self.log.info(f"  Audio Frames Discarded: {stats['total_audio_frames_discarded']}")
        self.log.info("")
        self.log.info("TOOL CALLS:")
        self.log.info(f"  Total: {stats['total_tool_calls']}")
        self.log.info(f"  Canceled: {stats['canceled_tool_calls']}")
        self.log.info(f"  Cancellation Rate: {stats['cancellation_rate_pct']:.1f}%")
        self.log.info("=" * 60)
