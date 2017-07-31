# -*- coding:utf-8 -*-

import commands
import re

from checks import AgentCheck


class SquidCheck(AgentCheck):

  def __init__(self, name, init_config, agentConfig, instances=None):
    AgentCheck.__init__(self, name, init_config, agentConfig, instances)
    self.get_values()


  def check(self, instance):
    if "target" not in instance:
      self.log.warn("Skipping instance, no target found.")

    default_pattern = self.init_config.get("default_pattern")
    pattern = instance.get("pattern", default_pattern)

    if self.status == 0:
        self.gauge("squid.alive",1)
        self.fetch(instance["target"], instance["metricname"],pattern)
    else:
        self.gauge("squid.alive",0)
        raise Exception("squid is not alive.")


  def get_values(self):
    self.status, self.values = commands.getstatusoutput("/bin/squidclient -p 3128 mgr:info")


  def fetch(self, target, metricname, pattern):
    try:
      result = re.search(target + pattern, self.values).group(1)
    except:
      self.log.warn("no value matched.")
    else:
      self.gauge(metricname, result)


if __name__ == "__main__":
  check, instances = SquidCheck.from_yaml("/etc/oneapm-ci-agent/conf.d/squid.yaml")

  for instance in instances:
    check.check(instance)

