#!/usr/bin/env bash
# Copies the Python package into the addon build context.
# Run this before building the Docker image.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGE_DIR="${SCRIPT_DIR}/package"

echo "Preparing addon build context..."

# Clean previous build artifacts
rm -rf "${PACKAGE_DIR}"
mkdir -p "${PACKAGE_DIR}"

# Copy package source and build files
cp -r "${REPO_ROOT}/src" "${PACKAGE_DIR}/src"
cp "${REPO_ROOT}/pyproject.toml" "${PACKAGE_DIR}/pyproject.toml"
cp "${REPO_ROOT}/README.md" "${PACKAGE_DIR}/README.md"

echo "Build context ready at ${PACKAGE_DIR}"
