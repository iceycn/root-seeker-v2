from __future__ import annotations

from typing import Any

from rootseeker.analysis.service_identity import resolve_service_name
from rootseeker.channel_routing.models import ChannelMessage, NormalizedInboundMessage

__all__ = ["normalize_inbound", "normalize_aliyun_alert", "normalize_sls_alert", "normalize_prometheus_alert"]


def normalize_inbound(message: ChannelMessage) -> NormalizedInboundMessage:
    """Normalize inbound message based on channel type."""
    channel = message.channel
    payload = message.payload

    # Channel-specific normalization
    if channel == "aliyun":
        return normalize_aliyun_alert(payload)
    if channel == "sls":
        return normalize_sls_alert(payload)
    if channel == "prometheus":
        return normalize_prometheus_alert(payload)

    # Default webhook normalization
    title = str(payload.get("title") or payload.get("alert_name") or "Untitled alert")
    symptom = str(payload.get("message") or payload.get("description") or payload.get("content") or title)
    service_name = resolve_service_name(
        payload.get("service_name"),
        payload.get("service"),
        text=symptom,
    )
    return NormalizedInboundMessage(
        channel=channel,
        tenant=str(payload.get("tenant") or "demo"),
        environment=str(payload.get("environment") or "prod"),
        service_name=service_name,
        severity=str(payload.get("severity") or "warning"),
        team=str(payload.get("team") or "unknown"),
        title=title,
        symptom=symptom,
        trace_id=str(payload["trace_id"]) if payload.get("trace_id") else None,
        metadata={k: v for k, v in payload.items() if k not in _RESERVED_KEYS},
    )


def normalize_aliyun_alert(payload: dict[str, Any]) -> NormalizedInboundMessage:
    """Normalize Alibaba Cloud alert webhook payload.

    Typical Aliyun alert structure:
    {
        "alertName": "...",
        "alertState": "ALARM",
        "curValue": "...",
        "instanceName": "...",
        "metricName": "...",
        "namespace": "...",
        ...
    }
    """
    alert_name = str(payload.get("alertName") or payload.get("alert_name") or "Aliyun Alert")
    instance = str(payload.get("instanceName") or payload.get("instance") or "unknown-instance")
    metric = str(payload.get("metricName") or payload.get("metric") or "unknown-metric")
    state = str(payload.get("alertState") or "ALARM")

    severity = "critical" if state == "ALARM" else "warning"

    title = f"[Aliyun] {alert_name}"
    symptom = f"{metric}={payload.get('curValue', 'N/A')} on {instance}"

    return NormalizedInboundMessage(
        channel="aliyun",
        tenant=str(payload.get("tenant") or "demo"),
        environment=str(payload.get("environment") or "prod"),
        service_name=instance,
        severity=severity,
        team=str(payload.get("team") or "unknown"),
        title=title,
        symptom=symptom,
        trace_id=str(payload.get("traceId")) if payload.get("traceId") else None,
        metadata={k: v for k, v in payload.items() if k not in _ALIYUN_RESERVED_KEYS},
    )


def normalize_sls_alert(payload: dict[str, Any]) -> NormalizedInboundMessage:
    """Normalize SLS (Simple Log Service) alert webhook payload.

    Typical SLS alert structure:
    {
        "alertName": "...",
        "project": "...",
        "logstore": "...",
        "query": "...",
        "count": 10,
        "message": "...",
        ...
    }
    """
    alert_name = str(payload.get("alertName") or payload.get("alert_name") or "SLS Alert")
    project = str(payload.get("project") or "unknown-project")
    logstore = str(payload.get("logstore") or "unknown-logstore")
    count = int(payload.get("count") or 0)

    title = f"[SLS] {alert_name}"
    symptom = f"Found {count} matches in {project}/{logstore}: {payload.get('message', '')}"

    return NormalizedInboundMessage(
        channel="sls",
        tenant=str(payload.get("tenant") or "demo"),
        environment=str(payload.get("environment") or "prod"),
        service_name=project,
        severity=str(payload.get("severity") or "warning"),
        team=str(payload.get("team") or "unknown"),
        title=title,
        symptom=symptom,
        trace_id=str(payload.get("traceId")) if payload.get("traceId") else None,
        metadata={k: v for k, v in payload.items() if k not in _SLS_RESERVED_KEYS},
    )


def normalize_prometheus_alert(payload: dict[str, Any]) -> NormalizedInboundMessage:
    """Normalize Prometheus Alertmanager webhook payload.

    Typical Prometheus alert structure:
    {
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "...", "service": "..."},
            "annotations": {"summary": "...", "description": "..."},
        }],
        "status": "firing",
        ...
    }
    """
    alerts = payload.get("alerts") or []
    status = str(payload.get("status") or "firing")

    if alerts:
        first_alert = alerts[0]
        labels = first_alert.get("labels") or {}
        annotations = first_alert.get("annotations") or {}

        alert_name = str(labels.get("alertname") or "Prometheus Alert")
        service = str(labels.get("service") or labels.get("job") or "unknown-service")
        summary = str(annotations.get("summary") or annotations.get("description") or alert_name)

        severity = "critical" if status == "firing" else "warning"

        title = f"[Prometheus] {alert_name}"
        symptom = summary

        return NormalizedInboundMessage(
            channel="prometheus",
            tenant=str(labels.get("tenant") or "demo"),
            environment=str(labels.get("environment") or "prod"),
            service_name=service,
            severity=severity,
            team=str(labels.get("team") or "unknown"),
            title=title,
            symptom=symptom,
            trace_id=str(labels.get("trace_id")) if labels.get("trace_id") else None,
            metadata={
                "labels": dict(labels),
                "annotations": dict(annotations),
                "alert_count": len(alerts),
            },
        )

    # Fallback for empty alerts
    return NormalizedInboundMessage(
        channel="prometheus",
        tenant="demo",
        environment="prod",
        service_name="unknown-service",
        severity="warning",
        team="unknown",
        title="[Prometheus] Alert",
        symptom="No alert details provided",
        trace_id=None,
        metadata={},
    )


_RESERVED_KEYS = {
    "title",
    "alert_name",
    "message",
    "description",
    "tenant",
    "environment",
    "service_name",
    "service",
    "severity",
    "team",
    "trace_id",
    "_channel",
}

_ALIYUN_RESERVED_KEYS = {
    "alertName",
    "alert_name",
    "alertState",
    "curValue",
    "instanceName",
    "instance",
    "metricName",
    "metric",
    "namespace",
    "tenant",
    "environment",
    "team",
    "traceId",
    "severity",
}

_SLS_RESERVED_KEYS = {
    "alertName",
    "alert_name",
    "project",
    "logstore",
    "query",
    "count",
    "message",
    "tenant",
    "environment",
    "team",
    "traceId",
    "severity",
}
