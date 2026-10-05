#!/usr/bin/env bash
# Run the snn_hello ROS2 node.
# Run this script inside the container: bash scripts/run_snn_hello.sh
set -euo pipefail

echo "==> Sourcing ROS2 Humble underlay and workspace overlay..."
# ROS2's setup.bash references unset variables, which trips `set -u`.
set +u
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash
# shellcheck source=/dev/null
source /workspace/ros2_ws/install/setup.bash
set -u

echo "==> Launching snn_hello_node ..."
ros2 run snn_hello snn_hello_node
