from setuptools import setup, find_packages

setup(
    name="cimo",
    version="1.0.0",
    description="CIMO v1: Physically Grounded Benchmark for Heterogeneous Autonomous Mission Operations",
    packages=find_packages(exclude=["tests*", "tools*"]),
    python_requires=">=3.9",
    install_requires=[
        "pyyaml>=6.0",
    ],
    extras_require={
        "rl": ["gymnasium>=0.29"],
        "dev": ["pytest>=7.0"],
    },
)
