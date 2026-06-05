"""Watchtower data source client - queries local LGTM stack."""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..config import settings


class WatchtowerClient:
    """Client for querying Watchtower's LGTM stack."""

    def __init__(
        self,
        loki_url: str | None = None,
        tempo_url: str | None = None,
        prometheus_url: str | None = None,
        sonarqube_url: str | None = None,
        sonarqube_token: str | None = None,
        timeout: float = 30.0,
    ):
        self.loki_url = loki_url or settings.watchtower_loki_url
        self.tempo_url = tempo_url or settings.watchtower_tempo_url
        self.prometheus_url = prometheus_url or settings.watchtower_prometheus_url
        self.sonarqube_url = sonarqube_url or settings.sonarqube_url
        self.sonarqube_token = sonarqube_token or settings.sonarqube_token
        self.timeout = timeout

    # =========================================================================
    # Health checks
    # =========================================================================

    async def check_loki_health(self) -> tuple[bool, float]:
        """Check Loki health. Returns (healthy, latency_ms)."""
        start = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.loki_url}/ready")
                latency = (datetime.now() - start).total_seconds() * 1000
                return resp.status_code == 200, latency
        except Exception:
            latency = (datetime.now() - start).total_seconds() * 1000
            return False, latency

    async def check_tempo_health(self) -> tuple[bool, float]:
        """Check Tempo health. Returns (healthy, latency_ms)."""
        start = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.tempo_url}/ready")
                latency = (datetime.now() - start).total_seconds() * 1000
                return resp.status_code == 200, latency
        except Exception:
            latency = (datetime.now() - start).total_seconds() * 1000
            return False, latency

    async def check_prometheus_health(self) -> tuple[bool, float]:
        """Check Prometheus health. Returns (healthy, latency_ms)."""
        start = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.prometheus_url}/-/healthy")
                latency = (datetime.now() - start).total_seconds() * 1000
                return resp.status_code == 200, latency
        except Exception:
            latency = (datetime.now() - start).total_seconds() * 1000
            return False, latency

    async def check_sonarqube_health(self) -> tuple[bool, float]:
        """Check SonarQube health. Returns (healthy, latency_ms)."""
        start = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.sonarqube_url}/api/system/status")
                latency = (datetime.now() - start).total_seconds() * 1000
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("status") == "UP", latency
                return False, latency
        except Exception:
            latency = (datetime.now() - start).total_seconds() * 1000
            return False, latency

    # =========================================================================
    # Loki (Logs)
    # =========================================================================

    async def query_loki_logs(
        self,
        query: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Query Loki for logs matching a LogQL query.

        Args:
            query: LogQL query string, e.g. '{service_name="my-app"} |= "error"'
            start_time: Start of time range (default: 1 hour ago)
            end_time: End of time range (default: now)
            limit: Maximum number of log lines to return

        Returns:
            List of log entries with timestamp, labels, and line
        """
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(hours=1)

        params = {
            "query": query,
            "start": int(start_time.timestamp() * 1e9),  # Nanoseconds
            "end": int(end_time.timestamp() * 1e9),
            "limit": limit,
            "direction": "backward",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for value in stream.get("values", []):
                timestamp_ns, line = value
                results.append({
                    "timestamp": datetime.fromtimestamp(int(timestamp_ns) / 1e9).isoformat(),
                    "labels": labels,
                    "line": line,
                })
        return results

    async def query_loki_errors(
        self,
        service_name: str | None = None,
        error_code: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Query Loki for error logs, optionally filtered by service and error code.

        Args:
            service_name: Filter by service name
            error_code: Filter by error code in log line
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of log lines

        Returns:
            List of error log entries
        """
        # Build LogQL query
        label_matchers = []
        if service_name:
            label_matchers.append(f'service_name="{service_name}"')

        if label_matchers:
            query = "{" + ", ".join(label_matchers) + "}"
        else:
            query = '{job=~".+"}'  # Match any job

        # Add error filter
        query += ' |~ "(?i)(error|exception|traceback|failed)"'

        if error_code:
            query += f' |= "{error_code}"'

        return await self.query_loki_logs(query, start_time, end_time, limit)

    # =========================================================================
    # Tempo (Traces)
    # =========================================================================

    async def search_traces(
        self,
        service_name: str | None = None,
        min_duration_ms: int | None = None,
        max_duration_ms: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search Tempo for traces.

        Args:
            service_name: Filter by service name
            min_duration_ms: Minimum trace duration in milliseconds
            max_duration_ms: Maximum trace duration in milliseconds
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of traces

        Returns:
            List of trace summaries with traceID, rootServiceName, duration, etc.
        """
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(hours=1)

        params: dict[str, Any] = {
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp()),
            "limit": limit,
        }

        # Build tags query
        tags = []
        if service_name:
            tags.append(f'service.name="{service_name}"')
        if min_duration_ms:
            params["minDuration"] = f"{min_duration_ms}ms"
        if max_duration_ms:
            params["maxDuration"] = f"{max_duration_ms}ms"

        if tags:
            params["tags"] = " && ".join(tags)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.tempo_url}/api/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        return data.get("traces", [])

    async def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        """
        Get a full trace by ID.

        Args:
            trace_id: The trace ID

        Returns:
            Full trace data or None if not found
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.tempo_url}/api/traces/{trace_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def search_error_traces(
        self,
        service_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search for traces with errors (status.code = ERROR).

        Args:
            service_name: Filter by service name
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of traces

        Returns:
            List of error trace summaries
        """
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(hours=1)

        params: dict[str, Any] = {
            "start": int(start_time.timestamp()),
            "end": int(end_time.timestamp()),
            "limit": limit,
            "tags": 'status.code="ERROR"',
        }

        if service_name:
            params["tags"] += f' && service.name="{service_name}"'

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.tempo_url}/api/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        return data.get("traces", [])

    # =========================================================================
    # Prometheus (Metrics)
    # =========================================================================

    async def query_prometheus(
        self,
        query: str,
        time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute an instant PromQL query.

        Args:
            query: PromQL query string
            time: Evaluation time (default: now)

        Returns:
            List of metric results with metric labels and value
        """
        params: dict[str, Any] = {"query": query}
        if time:
            params["time"] = time.timestamp()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.prometheus_url}/api/v1/query", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            raise ValueError(f"Prometheus query failed: {data.get('error', 'unknown error')}")

        results = []
        for result in data.get("data", {}).get("result", []):
            metric = result.get("metric", {})
            value = result.get("value", [None, None])
            results.append({
                "metric": metric,
                "timestamp": value[0],
                "value": value[1],
            })
        return results

    async def query_error_rate(
        self,
        service_name: str | None = None,
        window: str = "5m",
    ) -> list[dict[str, Any]]:
        """
        Query error rate metrics.

        Args:
            service_name: Filter by service name
            window: Rate window (e.g., "5m", "1h")

        Returns:
            Error rate metrics
        """
        if service_name:
            query = f'rate(http_server_request_count_total{{service_name="{service_name}",status_code=~"5.."}}[{window}])'
        else:
            query = f'rate(http_server_request_count_total{{status_code=~"5.."}}[{window}])'

        return await self.query_prometheus(query)

    # =========================================================================
    # SonarQube (Static Analysis)
    # =========================================================================

    async def get_sonarqube_issues(
        self,
        project_key: str,
        severities: list[str] | None = None,
        types: list[str] | None = None,
        file_path: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get SonarQube issues for a project.

        Args:
            project_key: SonarQube project key
            severities: Filter by severities (BLOCKER, CRITICAL, MAJOR, MINOR, INFO)
            types: Filter by types (BUG, VULNERABILITY, CODE_SMELL)
            file_path: Filter by file path
            limit: Maximum number of issues

        Returns:
            List of issues with rule, severity, component, message, etc.
        """
        params: dict[str, Any] = {
            "projectKeys": project_key,
            "ps": limit,  # Page size
        }

        if severities:
            params["severities"] = ",".join(severities)
        if types:
            params["types"] = ",".join(types)
        if file_path:
            params["componentKeys"] = f"{project_key}:{file_path}"

        headers = {}
        if self.sonarqube_token:
            # SonarQube uses token as username with empty password
            import base64
            auth = base64.b64encode(f"{self.sonarqube_token}:".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.sonarqube_url}/api/issues/search",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return data.get("issues", [])

    # =========================================================================
    # Data export
    # =========================================================================

    def write_logs_to_csv(
        self,
        logs: list[dict[str, Any]],
        output_path: Path,
    ) -> None:
        """
        Write log entries to a CSV file.

        Args:
            logs: List of log entries from query_loki_logs
            output_path: Path to write CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not logs:
            return

        # Flatten labels into columns
        fieldnames = ["timestamp", "line"]
        all_labels = set()
        for log in logs:
            all_labels.update(log.get("labels", {}).keys())
        fieldnames.extend(sorted(all_labels))

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for log in logs:
                row = {
                    "timestamp": log["timestamp"],
                    "line": log["line"],
                    **log.get("labels", {}),
                }
                writer.writerow(row)

    def write_traces_to_csv(
        self,
        traces: list[dict[str, Any]],
        output_path: Path,
    ) -> None:
        """
        Write trace summaries to a CSV file.

        Args:
            traces: List of trace summaries from search_traces
            output_path: Path to write CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not traces:
            return

        fieldnames = ["traceID", "rootServiceName", "rootTraceName", "durationMs", "startTimeUnixNano"]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for trace in traces:
                writer.writerow({
                    "traceID": trace.get("traceID"),
                    "rootServiceName": trace.get("rootServiceName"),
                    "rootTraceName": trace.get("rootTraceName"),
                    "durationMs": trace.get("durationMs"),
                    "startTimeUnixNano": trace.get("startTimeUnixNano"),
                })
