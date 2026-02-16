
import gi
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk
import os

print("--- GDK Monitors ---")
display = Gdk.Display.get_default()
if display:
    monitors_list = display.get_monitors() # Renamed to monitors_list to avoid confusion
    for i in range(monitors_list.get_n_items()):
        monitor = monitors_list.get_item(i)
        print(f"GDK Name: {monitor.get_connector()}")
        print(f"Model: {monitor.get_model()}")

print("\n--- DRM Connectors ---")
try:
    for p in sorted(os.listdir('/sys/class/drm')):
        if '-' in p and not p.startswith('version') and not p.startswith('card'): # Filter better
             continue 
        if p.startswith('card0-') or p.startswith('card1-'): # Typical naming
            connector_name = p.split('-', 1)[1]
            status_path = os.path.join('/sys/class/drm', p, 'status')
            if os.path.exists(status_path):
                with open(status_path, 'r') as f:
                    status = f.read().strip()
                print(f"DRM: {connector_name} ({status})")
except Exception as e:
    print(f"DRM Error: {e}")

print("\n--- Listing card0- connectors directly ---")
try:
    card0_path = '/sys/class/drm'
    for item in sorted(os.listdir(card0_path)):
        if item.startswith('card') and '-' in item:
             status_path = os.path.join(card0_path, item, 'status')
             if os.path.exists(status_path):
                 with open(status_path, 'r') as f: status = f.read().strip()
                 print(f"{item}: {status}")
except Exception as e: print(e)
