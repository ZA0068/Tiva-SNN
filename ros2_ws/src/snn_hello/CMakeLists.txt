cmake_minimum_required(VERSION 3.14)
project(snn_hello)

# Require C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)

add_executable(snn_hello_node src/hello_world.cpp)
ament_target_dependencies(snn_hello_node rclcpp)

install(TARGETS snn_hello_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
