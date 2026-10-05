FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# ── 1. Base tools ─────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        ca-certificates \
        lsb-release \
        software-properties-common \
        git \
        make \
        cmake \
        python3-pip \
        wget \
    && rm -rf /var/lib/apt/lists/*

# ── 2. ARM bare-metal toolchain ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc-arm-none-eabi \
        binutils-arm-none-eabi \
        libnewlib-arm-none-eabi \
        libstdc++-arm-none-eabi-newlib \
    && rm -rf /var/lib/apt/lists/*

# ── 3. lm4flash — build from source ──────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        libusb-1.0-0-dev \
        build-essential \
        pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/utzig/lm4tools.git /tmp/lm4tools \
    && cd /tmp/lm4tools/lm4flash \
    && make \
    && cp lm4flash /usr/local/bin/ \
    && rm -rf /tmp/lm4tools

# ── 4. ROS2 Humble ────────────────────────────────────────────────────────────
# GPG key must be added before the apt source line, and apt-get update
# must run after the source line is in place.
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && echo \
        "deb [arch=amd64 signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main" \
        > /etc/apt/sources.list.d/ros2.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-ros-base \
        python3-colcon-common-extensions \
        python3-rosdep \
    && rm -rf /var/lib/apt/lists/* \
    && rosdep init || true

# ── 5. ROS2 workspace — build ─────────────────────────────────────────────────
WORKDIR /workspace
COPY ros2_ws/ /workspace/ros2_ws/

RUN bash -c "\
    source /opt/ros/humble/setup.bash \
    && cd /workspace/ros2_ws \
    && rosdep update \
    && rosdep install --from-paths src --ignore-src -r -y \
    && colcon build"

# ── 6. Persistent shell sourcing ──────────────────────────────────────────────
RUN echo "source /opt/ros/humble/setup.bash" >> /etc/bash.bashrc \
    && echo "source /workspace/ros2_ws/install/setup.bash" >> /etc/bash.bashrc

# ── 7. TIVA sources ───────────────────────────────────────────────────────────
COPY tiva/ /workspace/tiva/

# ── 8. Default command ────────────────────────────────────────────────────────
CMD ["/bin/bash"]
