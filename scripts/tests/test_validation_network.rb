require "minitest/autorun"
require_relative "../../automation/vagrant/validation_network"

class NetworkConfigTest < Minitest::Test
  def config
    { "controller_ip" => "192.0.2.10", "platform_ip" => "192.0.2.20",
      "infrastructure_network" => { "segment_id" => "ci-existing-segment",
        "gateway" => "198.51.100.1", "dns" => "203.0.113.53",
        "addresses" => { "srv01-validation" => "198.51.100.20/24" } } }
  end
  def test_legacy
    assert_nil ValidationNetwork.validate({})
  end
  def test_valid
    assert_equal config["infrastructure_network"], ValidationNetwork.validate(config)
  end
  def test_bad_inputs
    ["invalid", "198.51.100.20/99", "198.51.100.0/24", "192.0.2.20/24"].each do |address|
      c=config;c["infrastructure_network"]["addresses"]["srv01-validation"]=address
      assert_raises(StandardError) { ValidationNetwork.validate(c) }
    end
    c=config;c["infrastructure_network"]["gateway"]="203.0.113.1"
    assert_raises(StandardError) { ValidationNetwork.validate(c) }
  end
  def test_no_recovery_or_duplicates
    c=config;c["infrastructure_network"]["addresses"]["srv01-recovery"]="198.51.100.30/24"
    assert_raises(StandardError) { ValidationNetwork.validate(c) }
    c=config;c["infrastructure_network"]["addresses"]["automation-controller"]="198.51.100.20/24"
    assert_raises(StandardError) { ValidationNetwork.validate(c) }
  end
end
