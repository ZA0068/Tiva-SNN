// =============================================================================
// SNN Hello World - ROS2 C++ node placeholder.
// Replace this with your SNN logic.
// =============================================================================

#include <rclcpp/rclcpp.hpp>

class SnnHelloNode : public rclcpp::Node
{
public:
  SnnHelloNode()
  : Node("snn_hello_node"), tick_(0)
  {
    timer_ = create_wall_timer(
      std::chrono::seconds(1),
      [this]() {
        RCLCPP_INFO(get_logger(), "Hello from SNN node! [tick %zu]", ++tick_);
      });
  }

private:
  rclcpp::TimerBase::SharedPtr timer_;
  std::size_t tick_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<SnnHelloNode>());
  rclcpp::shutdown();
  return 0;
}
