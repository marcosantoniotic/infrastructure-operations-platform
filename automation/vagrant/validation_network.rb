require "ipaddr"

# Pure validation, also exercised without loading Vagrant or starting any VM.
module ValidationNetwork
  MACHINES = %w[automation-controller srv01-validation srv02-standby].freeze

  def self.validate(config)
    net = config["infrastructure_network"]
    return nil if net.nil?
    raise "Infrastructure network must be an object" unless net.is_a?(Hash)
    id = net["segment_id"]
    raise "Existing LAN Segment ID required" unless id.is_a?(String) && !id.empty? && id.length <= 256 && !id.match?(/[\x00-\x1f]/)
    gateway = ipv4(net.fetch("gateway"))
    ipv4(net.fetch("dns"))
    addresses = net.fetch("addresses")
    raise "Service addresses must be a nonempty object" unless addresses.is_a?(Hash) && !addresses.empty?
    raise "Recovery/unknown guests require a separate network design" unless (addresses.keys - MACHINES).empty?
    raise "Standby guest is not configured" if addresses.key?("srv02-standby") && !config.key?("standby_ip")
    seen = []
    addresses.each_value do |cidr|
      raise "IPv4 CIDR required" unless cidr.is_a?(String) && cidr.match?(%r{\A[0-9.]+/[0-9]{1,2}\z})
      raw, prefix = cidr.split("/")
      raise "Usable subnet prefix required" unless (1..30).cover?(prefix.to_i)
      ip = ipv4(raw)
      subnet = IPAddr.new(cidr)
      range = subnet.to_range
      raise "Unusable service IP or gateway" unless subnet.include?(gateway) && ip != gateway &&
        ![range.first, range.last].include?(ip) && ![range.first, range.last].include?(gateway)
      raise "Duplicate service address" if seen.include?(ip)
      seen << ip
      %w[controller_ip platform_ip standby_ip recovery_ip].each do |key|
        next unless config[key]
        raise "Service subnet overlaps management addresses" if subnet.include?(IPAddr.new(config[key]))
      end
    end
    net
  end

  def self.ipv4(value)
    raise "IPv4 address required" unless value.is_a?(String) && !value.include?("/")
    ip = IPAddr.new(value)
    raise "Unicast IPv4 address required" unless ip.ipv4? && ip != IPAddr.new("0.0.0.0") &&
      !IPAddr.new("127.0.0.0/8").include?(ip) && ip.to_i < (224 << 24)
    ip
  end
end
