from setuptools import setup, find_packages

setup(
    name="llm-watchdog",
    version="1.0.2",
    description="Production-grade silent failure detection for LLM applications — hallucination alerts, PII leak detection, semantic drift, topic guard, and real-time observability",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/maheshmakvana/llm-watchdog",
    packages=find_packages(exclude=["tests*", "venv*", "llm-watchdog*", "build*"]),
    python_requires=">=3.8",
    install_requires=[
        "pydantic>=2.0",
    ],
    extras_require={
        "fastapi": ["fastapi>=0.100.0", "starlette>=0.27.0"],
        "flask": ["flask>=2.0.0"],
        "opentelemetry": ["opentelemetry-sdk>=1.20.0", "opentelemetry-api>=1.20.0"],
        "all": [
            "fastapi>=0.100.0",
            "starlette>=0.27.0",
            "flask>=2.0.0",
            "opentelemetry-sdk>=1.20.0",
            "opentelemetry-api>=1.20.0",
        ],
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.21"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
    ],
    keywords=[
        "llm monitoring", "ai observability", "hallucination detection",
        "pii detection", "semantic drift", "production ai", "llm alerts",
        "ai safety", "prompt monitoring", "silent failure detection",
        "llm quality", "ai production monitoring", "topic drift",
        "ai reliability", "llm guardrails",
    ],
    entry_points={
        "console_scripts": [
            "llm-watchdog=llm_watchdog.cli:main",
        ],
    },
)
