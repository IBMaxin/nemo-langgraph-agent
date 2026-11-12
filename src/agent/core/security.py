import ipaddress
import os
import re
import socket
import urllib.parse

from nemoguardrails.actions import action

from src.agent.core.logger import get_logger

logger = get_logger("security")

DEFAULT_PROTECTED_PATHS = [
    r"c:\windows",
    r"c:\program files",
    r"c:\program files (x86)",
    "/etc",
    "/root",
    "/bin",
    "/sbin",
    "/var/run",
]

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-Grade NAT & Tailscale
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local & cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

DESTRUCTIVE_CODE_PATTERNS = [
    (re.compile(r"\.\.[/\\]"), "Directory traversal ('../' or '..\\') is not allowed."),
    (
        re.compile(r"os\.(remove|unlink|rmdir|system)"),
        "Direct file deletion or os.system calls are blocked.",
    ),
    (
        re.compile(r"shutil\.(rmtree|move)"),
        "shutil deletion and move calls are blocked.",
    ),
    (
        re.compile(r"Path\([^)]*\)\.(unlink|rmdir)"),
        "Pathlib deletion calls are blocked.",
    ),
    (
        re.compile(
            r"subprocess\.(run|Popen|call|check_call|check_output)\s*\([^)]*(rm|del|rmdir|rd|Remove-Item|format)",
            re.IGNORECASE,
        ),
        "Destructive subprocess shell calls are blocked.",
    ),
    (
        re.compile(r"format\s+[a-zA-Z]:", re.IGNORECASE),
        "Disk format calls are blocked.",
    ),
]

INJECTION_PATTERNS = [
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions"),
    re.compile(r"(?i)disregard\s+(all\s+)?(previous|prior)\s+(prompts|rules|instructions)"),
    re.compile(r"(?i)you\s+are\s+now\s+(in\s+)?(dan|developer|jailbreak)\s+mode"),
    re.compile(r"(?i)system\s+prompt\s+override"),
    re.compile(r"(?i)new\s+system\s+directive:?"),
    re.compile(r"(?i)bypass\s+(system\s+)?(safety|guardrails)"),
]


def _get_protected_paths() -> list[str]:
    paths = list(DEFAULT_PROTECTED_PATHS)
    extra = os.getenv("ADDITIONAL_PROTECTED_PATHS", "").strip()
    if extra:
        for p in extra.split(","):
            clean = p.strip()
            if clean:
                paths.append(clean)
    return paths


def is_path_safe(target_path: str) -> bool:
    """Checks whether target_path avoids protected OS or configured directories."""
    try:
        norm = os.path.normpath(os.path.abspath(target_path)).lower()
        for protected in _get_protected_paths():
            if norm.startswith(protected.lower()):
                logger.warning(
                    f"Path blocked: '{target_path}' matched protected rule '{protected}'"
                )
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking path '{target_path}': {e}")
        return False


def is_url_safe(url: str) -> tuple[bool, str]:
    """SSRF check: ensures URL is public HTTP/HTTPS and does not resolve to private IPs."""
    if not url or not isinstance(url, str):
        return False, "Invalid URL provided."

    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        return (
            False,
            f"Unsupported scheme '{parsed.scheme}'. Only http and https are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        return False, "Could not extract hostname from URL."

    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "localtest.me"):
        logger.warning(f"SSRF blocked: direct loopback host '{hostname}'")
        return False, "I am not permitted to access internal network addresses."

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        logger.warning(f"DNS lookup failed for '{hostname}': {e}")
        return False, f"Could not resolve hostname '{hostname}'."

    for family, _, _, _, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            for network in BLOCKED_IP_NETWORKS:
                if ip_obj in network:
                    logger.warning(
                        f"SSRF blocked: '{url}' resolved to internal IP '{ip_str}' in {network}"
                    )
                    return (
                        False,
                        "I am not permitted to access internal network addresses.",
                    )
        except ValueError:
            continue

    return True, "URL is safe."


def is_code_safe(code: str) -> tuple[bool, str]:
    """Scans Python code string for path traversal and destructive functions."""
    if not code or not code.strip():
        return False, "Code snippet is empty."

    for pattern, reason in DESTRUCTIVE_CODE_PATTERNS:
        if pattern.search(code):
            logger.warning(f"Code blocked by pattern '{pattern.pattern}': {reason}")
            return (
                False,
                "I cannot execute destructive filesystem operations or directory traversals. Please rewrite your code to only create and modify files within the 'scratch/ephemeral/' path.",
            )

    return True, "Code passed check."


def sanitize_memory_content(content: str) -> tuple[str, bool, list[str]]:
    """Strips hidden HTML comments and prompt injection directives from text."""
    if not content or not isinstance(content, str):
        return content, False, []

    sanitized = content
    detected = []

    for pattern in INJECTION_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            detected.append(pattern.pattern)
            sanitized = pattern.sub("", sanitized)

    clean_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", sanitized).strip()
    was_modified = len(detected) > 0

    if was_modified:
        logger.warning(f"Sanitized memory input, removed patterns: {detected}")

    return clean_text, was_modified, detected


# NeMo action wrappers
@action(name="check_url_safety", is_system_action=True)
async def check_url_safety(url: str) -> bool:
    safe, _ = is_url_safe(url)
    return safe


@action(name="check_code_safety", is_system_action=True)
async def check_code_safety(code: str) -> bool:
    safe, _ = is_code_safe(code)
    return safe


@action(name="sanitize_memory_action", is_system_action=True)
async def sanitize_memory_action(content: str) -> str:
    clean, _, _ = sanitize_memory_content(content)
    return clean
