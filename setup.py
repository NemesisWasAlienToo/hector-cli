# SPDX-License-Identifier: AGPL-3.0-or-later
import os

from setuptools import setup, find_packages

_HERE = os.path.abspath(os.path.dirname(__file__))


def _read_readme():
    # README lives at the repo root (one level above this package dir); fall back
    # gracefully so the build never crashes if it's absent.
    for rel in ("README.md", os.path.join("..", "README.md")):
        path = os.path.join(_HERE, rel)
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
    return ""


setup(
    name="hector-cli",
    version="0.2.0",
    description="YAML-driven Renode + Verilator simulation orchestrator for embedded hardware CI",
    long_description=_read_readme(),
    long_description_content_type="text/markdown",
    author="Nemesis",
    author_email="info@hector-ci.com",
    url="https://hector-ci.com",
    license="AGPL-3.0-or-later",
    license_files=["LICENSE"],
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "pyyaml>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "hector=hector.pipeline:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Embedded Systems",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Programming Language :: Python :: 3",
    ],
)
