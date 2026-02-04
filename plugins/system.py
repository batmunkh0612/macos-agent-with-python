"""
System information plugin
"""

import os
import platform
import psutil
from datetime import datetime

def handle(args):
    """
    Get system information
    
    Args:
        args: {
            "info": "all" | "cpu" | "memory" | "disk" | "network"
        }
    """
    info_type = args.get('info', 'all')
    
    result = {}
    
    if info_type in ['all', 'cpu']:
        result['cpu'] = {
            "percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "load_avg": os.getloadavg() if hasattr(os, 'getloadavg') else None
        }
    
    if info_type in ['all', 'memory']:
        mem = psutil.virtual_memory()
        result['memory'] = {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used
        }
    
    if info_type in ['all', 'disk']:
        disk = psutil.disk_usage('/')
        result['disk'] = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent
        }
    
    if info_type in ['all', 'network']:
        net = psutil.net_io_counters()
        result['network'] = {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv
        }
    
    if info_type == 'all':
        result['system'] = {
            "platform": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "hostname": platform.node(),
            "uptime": datetime.now().timestamp() - psutil.boot_time()
        }
    
    return result
