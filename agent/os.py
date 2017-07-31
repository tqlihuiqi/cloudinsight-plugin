# -*- coding:utf-8 -*-

import threading
import time
import os
import re
import socket
import sys

from __future__ import division

from checks import AgentCheck


class SystemCheck(AgentCheck):

    def __init__(self, name, init_config, agentConfig, instances=None):
        AgentCheck.__init__(self, name, init_config, agentConfig, instances)
        self.interval = 1

    def check(self,instance):
        if "target" not in instance:
            self.log.warn("Skipping instance, no target found.")
        
        if hasattr(self,instance["target"]):
            if instance["target"] == "network":
                device = []
                for each in instance["interface"]:
                    device.append(each)
                if device: 
                    function = getattr(self,instance["target"])
                    thread = threading.Thread(name=instance["target"],target=function,args=(device,))
            else:
                function = getattr(self,instance["target"])
                thread = threading.Thread(name=instance["target"],target=function)
            thread.run()
        else:
            self.log.warn("Error, The target: %s not found." % instance["target"])


    def openfile(self, file_name):
        record = open(file_name, "r").readlines()
        return record
    

    def cut(self, dictionary, length=2):
        if isinstance(dictionary, dict):
            for k, v in dictionary.iteritems():
                dictionary[k] = round(float(v),length)

        return dictionary
    

    def to_Ci(self, metricname, dictionary):
        for k, v in dictionary.iteritems():
            self.gauge(metricname + k, v)


    def load(self):
        metric = {}
        record = self.openfile("/proc/loadavg")
        
        for index in range(len(record)):
            column = record[index].split()
        
        metric["1min"], metric["5min"], metric["15min"] = column[:3]
        self.to_Ci("os.load.", metric)


    def port(self,address="127.0.0.1", port=22):
        metric = {str(port): 0}
        s = socket.socket()
        
        try:
            s.connect((address, port))
            metric[str(port)] = 1
        except socket.error, e:
            pass
        
        self.to_Ci("os.port.", metric)


    def process(self):
        metric, status = {}, []
        processes = [ x for x in os.listdir("/proc") if x.isdigit() ]
        
        for each in processes:
            try:
                record = self.openfile("/proc/" + str(each) + "/stat")
            except IOError as ioErr:
                pass

            column = record[0].split()
            status.append(column[2])
        
        metric["total"] = len(status)
        metric["sleepping"] = status.count("S")
        metric["running"] = status.count("R")
        metric["stopped"] = status.count("T")
        metric["zombie"] = status.count("Z")
        self.to_Ci("os.process.", metric)
    

    def cpu(self):
        def sample():
            metric = {}
            record = self.openfile("/proc/stat")

            for row in record:
                column = row.split()
                
                if row.split()[0] == "cpu":
                    metric["user_ratio"], metric["nice_ratio"], metric["sys_ratio"], metric["idle_ratio"], metric["iowait_ratio"] = map(int,column[1:6])
                    metric["time"] = sum(map(int,column[1:6]))
                
                if row.split()[0] == "ctxt":
                    metric["csw"] =  int(column[1])
                
                if row.split()[0] == "intr":
                    metric["int"] =  int(column[1])
            
            return metric

        first  = sample() ; time.sleep(self.interval)
        second = sample()

        metric = {}
        cpu_time = second["time"] - first["time"]
        metric["csw"]   = second["csw"] - first["csw"]
        metric["int"]   = second["int"] - first["int"]
        metric["user_ratio"] = ( second["user_ratio"] - first["user_ratio"] ) / cpu_time * 100
        metric["nice_ratio"] = ( second["nice_ratio"] - first["nice_ratio"] ) / cpu_time * 100
        metric["sys_ratio"]  = ( second["sys_ratio"]  - first["sys_ratio"]  ) / cpu_time * 100
        metric["idle_ratio"] = ( second["idle_ratio"] - first["idle_ratio"] ) / cpu_time * 100
        metric["iowait_ratio"] = ( second["iowait_ratio"] - first["iowait_ratio"] ) / cpu_time * 100
        metric = self.cut(metric)
        
        self.to_Ci("os.cpu.", metric)
    

    def memory(self):
        metric = {}
        record = self.openfile("/proc/meminfo")
        
        for row in record:
            column = row.split()
            if row.split()[0] == "MemTotal:": metric["total_MB"]   = int(column[1]) / 1024
            if row.split()[0] == "MemFree:":  metric["free_MB"]    = int(column[1]) / 1024
            if row.split()[0] == "Buffers:":  metric["buffers_MB"] = int(column[1]) / 1024
            if row.split()[0] == "Cached:":   metric["cached_MB"]  = int(column[1]) / 1024
        
        metric["used_MB"]  = (metric["total_MB"] - metric["free_MB"])
        metric["util_ratio"] = (metric["total_MB"] - metric["free_MB"] - metric["buffers_MB"] - metric["cached_MB"]) / metric["total_MB"] * 100
        metric = self.cut(metric)
        
        self.to_Ci("os.memory.", metric)
    

    def swap(self):
        metric = {}
        record = self.openfile("/proc/meminfo")
        
        for row in record:
            column = row.split()
            if row.split()[0] == "SwapTotal:": metric["swap.total_MB"] = int(column[1]) / 1024
            if row.split()[0] == "SwapFree:":  metric["swap.free_MB"]  = int(column[1]) / 1024
        
        metric["swap.used_MB"]  = (metric["swap.total_MB"] - metric["swap.free_MB"]) / 1024
        
        try:
            metric["swap.util_ratio"] = metric["swap.used_MB"] / metric["swap.total_MB"] * 100
        except ZeroDivisionError as zeroErr:
            metric["swap.util_ratio"] = "0.0"
        
        metric = self.cut(metric)
        self.to_Ci("os.swap.", metric)
    

    def disk(self):
        def device():
            metric = {}
            devices = [ x for x in os.listdir("/sys/block") ]
            
            for disk in devices:
                metric[disk] = []
                parts = re.findall(disk + '\d+?',' '.join(os.listdir("/sys/block/" + disk)))
                
                for part in parts:
                    metric[disk].append(part)
            
            return metric
        
        device = device()

        def usage(part):
            metric = {}
            record = self.openfile("/etc/mtab")
            
            for row in record:
                if row.split()[0] == part:
                    statvfs = os.statvfs(row.split()[1])
                    metric["total_GB"] = statvfs.f_bsize * statvfs.f_blocks / pow(1024,3)
                    metric["free_GB"]  = statvfs.f_bsize * statvfs.f_bavail / pow(1024,3)
                    metric["used_GB"]  = statvfs.f_bsize * (statvfs.f_blocks - statvfs.f_bfree) / pow(1024,3)
                    metric["util_ratio"] = metric["used_GB"] / (metric["used_GB"] + metric["free_GB"]) * 100
            
            return metric

        def sample(disk,part):
            metric = {}
            record = self.openfile("/sys/block/" + disk + "/" + part + "/stat")
            column = record[0].split()
            metric["r/s"]    = int(column[0])
            metric["rrqm/s"] = int(column[1])
            metric["rMB/s"]  = int(column[2]) * 512 / pow(1024,2)
            metric["w/s"]    = int(column[4])
            metric["wrqm/s"] = int(column[5])
            metric["wMB/s"]  = int(column[6]) * 512 / pow(1024,2)
            metric["io/s"]   = int(column[0]) + int(column[4])
            metric["ticks"]  = int(column[9])

            return metric

        def fetch(device):
            metric = {}
            for k,v in device.iteritems():
                disk = k
                
                for part in v:
                    metric[part] = sample(disk,part)
            
            return metric

        for parts in device.itervalues():
            for part in parts:
                metric = self.cut(usage("/dev/" + part))
                self.to_Ci("os.disk."+ part + ".", metric)

        first  = fetch(device); time.sleep(self.interval)
        second = fetch(device)

        for parts in device.itervalues():
            for part in parts:    
                metric = {}
                metric["r/s"]    = second[part]["r/s"]    - first[part]["r/s"]
                metric["rrqm/s"] = second[part]["rrqm/s"] - first[part]["rrqm/s"]
                metric["rMB/s"]  = second[part]["rMB/s"]  - first[part]["rMB/s"]
                metric["w/s"]    = second[part]["w/s"]    - first[part]["w/s"]
                metric["wrqm/s"] = second[part]["wrqm/s"] - first[part]["wrqm/s"]
                metric["wMB/s"]  = second[part]["wMB/s"]  - first[part]["wMB/s"]
                metric["io/s"]   = second[part]["io/s"]   - first[part]["io/s"]
                
                try:
                    metric["svctm"] = ( second[part]["ticks"]  - first[part]["ticks"] ) / (metric["r/s"] + metric["w/s"])
                except ZeroDivisionError as zeroErr:
                    metric["svctm"] = 0.0
                
                metric["busy_ratio"]  = ( metric["r/s"] + metric["w/s"] ) * ( metric["svctm"] / 1000 ) * 100
                metric = self.cut(metric)
                
                self.to_Ci("os.disk."+ part + ".", metric)
    

    def network(self, interface):
        def device():
            realdev = []
            record = self.openfile("/proc/net/dev")
            
            for row in record:
                column = row.split()
                name = column[0].replace(":","")
            
                if name in interface:
                    realdev.append(name)
           
            return realdev
        
        interface = device()

        def sample():
            metric = {}
            record = self.openfile("/proc/net/dev")

            for row in record:
                column = row.split()
                name = column[0].replace(":","")

                if name in interface:
                    metric[name] = {}
                    metric[name]["inKB/s"], metric[name]["in_packs/s"], metric[name]["in_err_packs/s"], metric[name]["in_drp_packs/s"] = map(int,column[1:5])
                    metric[name]["outKB/s"], metric[name]["out_packs/s"], metric[name]["out_err_packs/s"], metric[name]["out_drp_packs/s"] = map(int,column[9:13])
            
            return metric

        first  = sample() ; time.sleep(self.interval)
        second = sample()

        metric = {}
        for netdev in interface:
            metric["inKB/s"]  = ( second[netdev]["inKB/s"]  - first[netdev]["inKB/s"]  ) / 1024
            metric["outKB/s"] = ( second[netdev]["outKB/s"] - first[netdev]["outKB/s"] ) / 1024
            metric["in_packs/s"] = second[netdev]["in_packs/s"] - first[netdev]["in_packs/s"]
            metric["in_err_packs/s"]  = second[netdev]["in_err_packs/s"]  - first[netdev]["in_err_packs/s"]
            metric["in_drp_packs/s"]  = second[netdev]["in_drp_packs/s"]  - first[netdev]["in_drp_packs/s"]
            metric["out_packs/s"]     = second[netdev]["out_packs/s"]     - first[netdev]["out_packs/s"]
            metric["out_err_packs/s"] = second[netdev]["out_err_packs/s"] - first[netdev]["out_err_packs/s"]
            metric["out_drp_packs/s"] = second[netdev]["out_drp_packs/s"] - first[netdev]["out_drp_packs/s"]
            metric = self.cut(metric)
            
            self.to_Ci("os.network." + netdev +".", metric)
    

    def tcp(self):
        metric, status = {}, []
        STATE  = { 
            "01":"ESTABLISHED", 
            "02":"SYN_SENT", 
            "03":"SYN_RECV", 
            "04":"FIN_WAIT1", 
            "05":"FIN_WAIT2", 
            "06":"TIME_WAIT", 
            "07":"CLOSE", 
            "08":"CLOSE_WAIT", 
            "09":"LAST_ACK", 
            "0A":"LISTEN", 
            "0B":"CLOSING" 
        } 
        record = self.openfile("/proc/net/tcp")

        for row in record:
            column = row.split()
            status.append(column[3])

        metric["estab"]      = status.count("01")
        metric["syn_sent"]   = status.count("02")
        metric["syn_recv"]   = status.count("03")
        metric["fin_wait1"]  = status.count("04")
        metric["fin_wait2"]  = status.count("05")
        metric["time_wait"]  = status.count("06")
        metric["close"]      = status.count("07")
        metric["close_wait"] = status.count("08")
        metric["last_ack"]   = status.count("09")
        metric["listen"]     = status.count("0A")
        metric["closing"]    = status.count("0B")

        self.to_Ci("os.tcp.", metric)

        def sample():
            metric, status = {}, []
            record = self.openfile("/proc/net/snmp")
            
            for row in record:
                column = row.split()

                if column[0] == "Tcp:":
                    status.append(column[1:])

            metric = dict(zip(status[0],map(int,status[1])))
            
            return metric

        first  = sample(); time.sleep(self.interval)
        second = sample()

        metric = {}
        metric["active/s"]   = second["ActiveOpens"]   - first["ActiveOpens"]
        metric["pasive/s"]   = second["PassiveOpens"]  - first["PassiveOpens"]
        metric["iseg/s"]     = second["InSegs"]        - first["InSegs"]
        metric["outseg/s"]   = second["OutSegs"]       - first["OutSegs"]
        metric["estReset/s"] = second["EstabResets"]   - first["EstabResets"]
        metric["atmpFail/s"] = second["AttemptFails"]  - first["AttemptFails"]
        
        try:
            metric["retran_ratio"] = ( second["RetransSegs"] - first["RetransSegs"] ) / metric["outseg/s"] * 100
        except ZeroDivisionError as zeroErr:
            metric["retran_ratio"] = 0.0
       
        metric = self.cut(metric)
        self.to_Ci("os.tcp.", metric)

if __name__ == "__main__":
    check, instances = SystemCheck.from_yaml("/etc/oneapm-ci-agent/conf.d/os.yaml")

    for instance in instances:
        check.check(instance)

