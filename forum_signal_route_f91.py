#!/usr/bin/env python3

import forum_signal_route as route


F91_EXTRA_ALIGNMENT = [
    "vibe code", "vibe coding", "llm", "agent", "agentic", "mcp", "api", "openrouter",
    "backend", "frontend", "fullstack", "data", "data engineer", "data analyst", "qa", "tester",
    "automation test", "embedded", "firmware", "vi mạch", "semiconductor", "system design",
    "microservice", "redis", "kafka", "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
    "sre", "remote", "offer", "fresher", "intern", "senior", "staff", "career", "nghề",
    "tuyển dụng", "nhảy việc", "sa thải", "layoff", "thạc sĩ", "xuất ngoại",
]

route.ALIGNMENT["VOZ-F91"] = list(dict.fromkeys(route.ALIGNMENT.get("VOZ-F91", []) + F91_EXTRA_ALIGNMENT))


if __name__ == "__main__":
    route.main()
