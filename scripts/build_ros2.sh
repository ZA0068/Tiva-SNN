#!/usr/bin/env bash
# Build the ROS2 workspace with colcon.
# Run this script inside the container: bash scripts/build_ros2.sh
set -euo pipefail

ROS2_WS="/workspace/ros2_ws"

echo "==> Sourcing ROS2 Humble underlay..."
# ROS2's setup.bash references unset variables, which trips `set -u`.
set +u
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash
set -u

echo "==> Building ROS2 workspace at ${ROS2_WS} ..."
cd "${ROS2_WS}"

if colcon build --symlink-install; then
    echo ""
    echo "✔  ROS2 build succeeded."
    echo "   Source the workspace before running nodes:"
    echo "   source ${ROS2_WS}/install/setup.bash"
else
    echo ""
    echo "✘  ROS2 build FAILED. Check the colcon output above for errors." >&2
    exit 1
fi
