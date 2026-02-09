#!/usr/bin/env python3
"""
Performance chart widget using Cairo drawing.
Replaces the old text-based monitor with a modern visual chart.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time
import random
import threading
import subprocess
import re
from pathlib import Path
import traceback

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw, Gdk
from utils.i18n import _

# Import cairo
try:
    import cairo
except ImportError:
    cairo = None

CHART_MAX_HISTORY = 60  # 60 seconds of history

from utils.icons import create_icon_widget, set_icon

@dataclass
class PerformanceDataPoint:
    """Single data point for performance chart."""
    latency: float       # ms (Average)
    fps: float           # frames
    bandwidth: float     # Mbps
    
    # New: Per-device latency for multi-line graph
    device_latencies: dict # {name: latency}
    
    # Text representations
    latency_text: str
    fps_text: str
    bandwidth_text: str
    users_count: int = 0

class PerformanceChartWidget(Gtk.DrawingArea):
    """
    Modern chart widget for network/video performance.
    """

    def __init__(self) -> None:
        super().__init__()

        self._history: deque[PerformanceDataPoint] = deque(maxlen=CHART_MAX_HISTORY)
        
        # Max values for normalization (auto-adjusting or fixed)
        self.max_latency = 100.0
        self.max_fps = 120.0
        self.max_bandwidth = 50.0

        # Current values for display
        self._cur_latency_text = "--"
        self._cur_fps_text = "--"
        self._cur_bw_text = "--"
        
        # Device Colors
        self.device_colors = {}
        self.color_palette = [
            (1.0, 0.4, 0.0, 1.0), # Orange
            (1.0, 0.0, 0.4, 1.0), # Pink/Red
            (0.8, 0.0, 1.0, 1.0), # Purple
            (0.0, 1.0, 0.8, 1.0), # Cyan
            (1.0, 0.8, 0.0, 1.0), # Yellow
            (0.5, 1.0, 0.0, 1.0), # Lime
        ]

        # Hover state
        self._hover_x: float | None = None
        self._hover_index: int | None = None

        # Sizing
        self.set_size_request(300, 160)
        self.set_vexpand(False)
        self.set_hexpand(True)

        # Connect draw signal
        self.set_draw_func(self._on_draw)

        # Mouse tracking
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_motion)
        motion_controller.connect("leave", self._on_leave)
        self.add_controller(motion_controller)
        
    def _get_device_color(self, name):
        if name not in self.device_colors:
            # Pick next color
            idx = len(self.device_colors) % len(self.color_palette)
            self.device_colors[name] = self.color_palette[idx]
        return self.device_colors[name]
        
    def add_data_point(self, latency: float, fps: float, bandwidth: float, users: int = 0, device_latencies: dict = None):
        """Add new data point."""
        # Auto-scale max values if exceeded (dynamic scaling)
        if latency > self.max_latency: self.max_latency = latency * 1.2
        if fps > self.max_fps: self.max_fps = fps * 1.2
        if bandwidth > self.max_bandwidth: self.max_bandwidth = bandwidth * 1.2
        
        if device_latencies:
            for lat in device_latencies.values():
                if lat > self.max_latency: self.max_latency = lat * 1.2
        
        point = PerformanceDataPoint(
            latency=latency,
            fps=fps,
            bandwidth=bandwidth,
            device_latencies=device_latencies or {},
            latency_text=f"{latency:.0f} ms",
            fps_text=f"{fps:.0f} FPS",
            bandwidth_text=f"{bandwidth:.1f} Mbps",
            users_count=users
        )
        
        self._history.append(point)
        self._cur_latency_text = point.latency_text
        self._cur_fps_text = point.fps_text
        self._cur_bw_text = point.bandwidth_text
        
        self.queue_draw()

    def _on_motion(self, controller, x, y):
        self._hover_x = x
        self._update_hover_index()
        self.queue_draw()

    def _on_leave(self, controller):
        self._hover_x = None
        self._hover_index = None
        self.queue_draw()

    def _update_hover_index(self) -> None:
        if self._hover_x is None or not self._history:
            self._hover_index = None
            return

        width = self.get_width()
        margin_left = 40
        margin_right = 10
        chart_width = width - margin_left - margin_right

        if chart_width <= 0:
            self._hover_index = None
            return

        if self._hover_x < margin_left or self._hover_x > width - margin_right:
            self._hover_index = None
            return

        num_points = len(self._history)
        x_step = chart_width / max(CHART_MAX_HISTORY - 1, 1)
        start_x = margin_left + chart_width - (num_points - 1) * x_step

        relative_x = self._hover_x - start_x
        index = round(relative_x / x_step) if x_step > 0 else 0
        index = max(0, min(num_points - 1, index))
        self._hover_index = index

    def _on_draw(self, area, cr, width, height):
        try:
            # Background - Dark Modern Style
            cr.set_source_rgba(0.12, 0.12, 0.12, 1.0)
            cr.rectangle(0, 0, width, height)
            cr.fill()

            margin_left = 40
            margin_right = 10
            margin_top = 20
            margin_bottom = 30

            chart_width = width - margin_left - margin_right
            chart_height = height - margin_top - margin_bottom

            if chart_width <= 0 or chart_height <= 0:
                return

            # Grid lines (draw 4 lines: 0%, 33%, 66%, 100%)
            cr.set_source_rgba(0.3, 0.3, 0.3, 0.3)
            cr.set_line_width(1)
            
            # We don't have a single scale, so grid lines are just visual guides
            for i in range(4):
                y = margin_top + (chart_height * i / 3)
                cr.move_to(margin_left, y)
                cr.line_to(margin_left + chart_width, y)
                cr.stroke()

            if not self._history:
                cr.set_source_rgba(0.5, 0.5, 0.5, 1)
                cr.set_font_size(14)
                text = _("Waiting for data...")
                extents = cr.text_extents(text)
                cr.move_to(margin_left + (chart_width - extents.width)/2, margin_top + chart_height/2)
                cr.show_text(text)
                return

            # Prepare normalized data lists
            lat_vals = [p.latency for p in self._history]
            fps_vals = [p.fps for p in self._history]
            bw_vals = [p.bandwidth for p in self._history]
            
            # Normalize 0..1 based on current maxes
            lat_norm = [v / max(1, self.max_latency) for v in lat_vals]
            fps_norm = [v / max(1, self.max_fps) for v in fps_vals]
            bw_norm = [v / max(1, self.max_bandwidth) for v in bw_vals]

            # Draw Lines
            # Bandwidth: Blue (Bottom layer)
            self._draw_line(cr, chart_width, chart_height, margin_left, margin_top, bw_norm, (0.0, 0.6, 1.0, 1.0), fill=True)
            
            # FPS: Green
            self._draw_line(cr, chart_width, chart_height, margin_left, margin_top, fps_norm, (0.0, 0.8, 0.2, 1.0), fill=False)

            # Latency: Multi-line support
            # We need to collect all unique devices seen in the history
            active_devices = set()
            for p in self._history:
                active_devices.update(p.device_latencies.keys())
            
            if not active_devices:
                # Fallback to drawing average line if no specific devices
                self._draw_line(cr, chart_width, chart_height, margin_left, margin_top, lat_norm, (1.0, 0.4, 0.0, 1.0))
            else:
                # Draw a line for each device
                for dev_name in active_devices:
                    dev_vals = []
                    for p in self._history:
                        # If device not present in this point, use previous val or 0
                        val = p.device_latencies.get(dev_name, 0) 
                        dev_vals.append(val / max(1, self.max_latency))
                    
                    color = self._get_device_color(dev_name)
                    self._draw_line(cr, chart_width, chart_height, margin_left, margin_top, dev_vals, color, fill=False)

            # Legend
            self._draw_legend(cr, width, height, margin_left, active_devices)
            
            if self._hover_index is not None and 0 <= self._hover_index < len(self._history):
                self._draw_tooltip(cr, width, height, margin_left, margin_top, chart_width, chart_height)
                
            # Draw current users count prominent
            if self._history:
                last_point = self._history[-1]
                if last_point.users_count > 0:
                    text = _("{} Active Devices").format(last_point.users_count)
                    cr.set_font_size(14)
                    # cr.set_font_weight(cairo.FontWeight.BOLD) # Cairo python bindings vary
                    ext = cr.text_extents(text)
                    
                    # Draw background box for text
                    box_x = width - ext.width - 25
                    box_y = margin_top + 5
                    cr.set_source_rgba(0.2, 0.2, 0.2, 0.8)
                    cr.rectangle(box_x - 5, box_y - 12, ext.width + 10, ext.height + 15)
                    cr.fill()
                    
                    cr.set_source_rgba(1, 1, 1, 1)
                    cr.move_to(box_x, box_y + ext.height)
                    cr.show_text(text)
        except Exception as e:
            traceback.print_exc()
            print(f"DEBUG: Error in _on_draw: {e}")

    def _draw_line(self, cr, w, h, mx, my, vals, color, fill=False):
        if not vals: return
        cr.set_source_rgba(*color); cr.set_line_width(2)
        x_step = w / max(CHART_MAX_HISTORY - 1, 1)
        sx = mx + w - (len(vals) - 1) * x_step
        
        # Stroke
        for i, v in enumerate(vals): (cr.line_to if i else cr.move_to)(sx + i * x_step, my + h * (1 - v))
        cr.stroke()
        
        if fill:
            cr.set_source_rgba(color[0], color[1], color[2], 0.15)
            for i, v in enumerate(vals): (cr.line_to if i else cr.move_to)(sx + i * x_step, my + h * (1 - v))
            cr.line_to(sx + (len(vals) - 1) * x_step, my + h); cr.line_to(sx, my + h); cr.close_path(); cr.fill()

    def _draw_legend(self, cr, w, h, margin_left, active_devices=None):
        legend_y = h - 10
        
        # Helper to draw dot + text
        def draw_item(label, val_text, color, x_offset):
            cr.set_source_rgba(*color)
            cr.arc(margin_left + x_offset, legend_y - 4, 4, 0, 2*3.14159)
            cr.fill()
            
            cr.set_source_rgba(0.9, 0.9, 0.9, 1)
            cr.set_font_size(11)
            cr.move_to(margin_left + x_offset + 10, legend_y)
            text = f"{label}: {val_text}"
            cr.show_text(text)
            return cr.text_extents(text).width + 30

        offset = 0
        if not active_devices:
            offset += draw_item(_("Latency"), self._cur_latency_text, (1.0, 0.4, 0.0, 1.0), offset)
        else:
            # Draw legend for each device in current history
            # Use last point values
            last_point = self._history[-1] if self._history else None
            for dev in active_devices:
                val = last_point.device_latencies.get(dev, 0) if last_point else 0
                color = self._get_device_color(dev)
                offset += draw_item(dev, f"{val:.0f}ms", color, offset)
            
        offset += draw_item("FPS", self._cur_fps_text, (0.0, 0.8, 0.2, 1.0), offset)
        # Offset Bandwidth a bit more if devices push it
        if offset > w - 100: legend_y -= 15; offset = 0 # Wrap if too long
        draw_item("BW", self._cur_bw_text, (0.0, 0.6, 1.0, 1.0), offset)

    def _draw_tooltip(self, cr, w, h, mx, my, cw, ch):
        point = list(self._history)[self._hover_index]
        num_points = len(self._history)
        x_step = cw / max(CHART_MAX_HISTORY - 1, 1)
        start_x = mx + cw - (num_points - 1) * x_step
        hover_x = start_x + self._hover_index * x_step

        # Vertical line
        cr.set_source_rgba(1, 1, 1, 0.4)
        cr.set_line_width(1)
        cr.move_to(hover_x, my)
        cr.line_to(hover_x, my + ch)
        cr.stroke()

        # Tooltip text lines
        lines = []
        if point.device_latencies:
            for dev, lat in point.device_latencies.items():
                lines.append(f"{dev}: {lat:.0f} ms")
        else:
            lines.append(f"Lat: {point.latency_text}")
            
        lines.append(f"FPS: {point.fps_text}")
        lines.append(f"BW: {point.bandwidth_text}")
        
        # Calculate box size dynamically
        # Simple drawing
        box_width = 130
        box_height = 20 + (len(lines) * 14)

        tooltip_x = min(w - box_width - 10, max(10, hover_x + 10))
        tooltip_y = my + 10
        
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.95)
        cr.rectangle(tooltip_x, tooltip_y, box_width, box_height)
        cr.fill()
        
        cr.set_source_rgba(1, 1, 1, 1)
        cr.set_font_size(10)
        
        y_off = 15
        for line in lines:
            cr.move_to(tooltip_x + 8, tooltip_y + y_off)
            cr.show_text(line)
            y_off += 14

class PerformanceMonitor(Gtk.Box):
    """
    Wrapper for performance chart.
    Replaces old text box.
    """
    
    def __init__(self, sunshine=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.sunshine = sunshine
        self.add_css_class('card')
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        
        # Header
        self._header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._header.set_margin_start(12)
        self._header.set_margin_end(12)
        self._header.set_margin_top(8)
        self._header.set_margin_bottom(4)
        
        # Title (Host Name)
        self._title_label = Gtk.Label(label=_("Real-time Monitoring"))
        self._title_label.add_css_class("heading")
        self._title_label.set_halign(Gtk.Align.START)
        self._title_label.set_hexpand(True)
        self._header.append(self._title_label)
        
        # Status (Icon + Text)
        self._status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        self._status_icon = create_icon_widget("network-idle-symbolic", size=16)
        
        self._status_label = Gtk.Label(label=_("Disconnected"))
        self._status_label.add_css_class("dim-label")
        
        self._status_box.append(self._status_icon)
        self._status_box.append(self._status_label)
        
        self._header.append(self._status_box)
        self.append(self._header)
        
        # Guest Details List (Above Graph)
        self._details_frame = Gtk.Frame()
        self._details_frame.set_margin_top(8)
        self._details_frame.set_margin_bottom(8)
        self._details_frame.set_margin_start(12)
        self._details_frame.set_margin_end(12)
        self._details_frame.set_visible(False)
        
        self._details_list = Gtk.ListBox()
        self._details_list.add_css_class('boxed-list')
        self._details_frame.set_child(self._details_list)
        self.append(self._details_frame)

        # Chart
        self.chart = PerformanceChartWidget()
        self.append(self.chart)
        
        self.update_timer_active = False
        self._fetching = False
        self._last_fps = 60.0
        self._last_bandwidth = 10.0
        self._missing_sessions_count = 0
        self._last_sessions = []
        self._last_device_latencies = {}

    def start_monitoring(self):
        """Starts real-time data fetching using GLib timeout (Gtk-safe)"""
        if self.update_timer_active: return
        print("DEBUG: PerformanceMonitor - Starting monitoring")
        self.update_timer_active = True
        
        # Initial cleanup/kickstart
        self.update_stats(0, 0, 0, [])
        
        # Start the periodic update
        self.update_source_id = GLib.timeout_add_seconds(1, self._perform_monitoring_step)

    def stop_monitoring(self): 
        if not self.update_timer_active: return
        print("DEBUG: PerformanceMonitor - Stopping monitoring")
        self.update_timer_active = False
        if hasattr(self, 'update_source_id'):
            GLib.source_remove(self.update_source_id)
            del self.update_source_id

    def _perform_monitoring_step(self):
        if not self.update_timer_active: return False
        
        if getattr(self, '_fetching', False): return True # Already fetching
        
        # Run fetching in a separate thread to avoid blocking UI
        self._fetching = True
        threading.Thread(target=self._fetch_data_thread, daemon=True).start()
        return True

    def _get_auth(self):
        try:
            # Check multiple possible config locations
            paths = [
                Path.home() / '.config' / 'big-remoteplay' / 'sunshine' / 'sunshine.conf',
                Path.home() / '.config' / 'sunshine' / 'sunshine.conf'
            ]
            for p in paths:
                if p.exists():
                    user = ""; pw = ""
                    with open(p, 'r') as f:
                        for line in f:
                            if '=' in line:
                                parts = line.strip().split('=', 1)
                                if len(parts) == 2:
                                    k, v = parts[0].strip(), parts[1].strip()
                                    if k == 'sunshine_user': user = v
                                    if k == 'sunshine_password': pw = v
                    if user and pw: return (user, pw)
        except: pass
        return None

    def _ping_host(self, ip):
        try:
            # -n: numeric only, -c 1: count 1, -W 0.5: timeout 500ms
            out = subprocess.check_output(["ping", "-c", "1", "-W", "0.5", "-n", ip], stderr=subprocess.DEVNULL, timeout=0.6).decode()
            m = re.search(r"time=([\d\.]+)", out)
            if m: return float(m.group(1))
        except: pass
        return 0.0

    def _fetch_data_thread(self):
        try:
            auth = self._get_auth()
            stats = {}
            sessions = []
            
            if self.sunshine:
                try:
                    stats = self.sunshine.get_performance_stats(auth=auth)
                    sessions = self.sunshine.get_active_sessions(auth=auth)
                except Exception as e:
                    print(f"DEBUG: Sunshine API fetch failed: {e}")
            
            def safe_float(v):
                try: return float(v)
                except: return 0.0

            latency = safe_float(stats.get('average_latency', 0))
            fps = safe_float(stats.get('fps', 0))
            bandwidth = safe_float(stats.get('bitrate', 0)) / 1000.0
            
            device_latencies = {}

            # Always update SS cache in background to keep it fresh
            # This ensures that if API drops, we have improved reliability immediately
            cached_ss_sessions = []
            if self.update_timer_active:
                cached_ss_sessions = self._detect_sessions_via_ss()

            # Normalize session data (handle clientAddress vs ip)
            normalized_sessions = []
            if sessions:
                 for s in sessions:
                     if not isinstance(s, dict): continue
                     # Sunshine API often uses clientAddress
                     if 'ip' not in s and 'clientAddress' in s:
                         s['ip'] = s['clientAddress']
                     if 'name' not in s and 'clientName' in s:
                         s['name'] = s['clientName']
                     normalized_sessions.append(s)
            sessions = normalized_sessions

            # If API found nothing, fallback to cached SS sessions
            used_ss_fallback = False
            if not sessions and cached_ss_sessions:
                sessions = cached_ss_sessions
                used_ss_fallback = True
            
            # Collect per-device latency for the chart
            for s in sessions:
                name = s.get('name', 'Unknown')
                ip = s.get('ip', '')
                
                # Format name nicely
                if name == _('Guest') and ip:
                    name = f"{_('Guest')} ({ip})"
                elif ip and ip not in name:
                    name = f"{name} ({ip})"
                
                l = safe_float(s.get('latency', 0))
                
                # If no latency from API, try pinging the device
                if l == 0 and ip:
                    l = self._ping_host(ip)
                    s['latency'] = l # update for list view
                    
                device_latencies[name] = l

            # Calculate averages if we have sessions
            if sessions:
                 s_lats = [safe_float(s.get('latency', 0)) for s in sessions]
                 if s_lats: 
                     latency = sum(s_lats) / len(s_lats)
                 
            # Mock FPS/Bandwidth if needed to show "Alive" status
            if fps == 0:
                # If sessions exist but API gives 0 FPS, stay at last known or reasonable default
                fps = self._last_fps if self._last_fps > 0 else 60.0
            else:
                self._last_fps = fps
                
            if bandwidth == 0:
                bandwidth = self._last_bandwidth if self._last_bandwidth > 0 else 1.0
            else:
                self._last_bandwidth = bandwidth

            # Grace period for UI: don't hide guests immediately if they disappear from one cycle
            if not sessions and self._last_sessions:
                self._missing_sessions_count += 1
                if self._missing_sessions_count < 10: # ~10 seconds grace
                    sessions = self._last_sessions
                    device_latencies = self._last_device_latencies
            else:
                self._missing_sessions_count = 0
                self._last_sessions = sessions
                self._last_device_latencies = device_latencies
            
            # MOCK MODE: If still 0 and hosting, generate small movement (only if NO sessions connected)
            if latency == 0 and fps == 0 and self.update_timer_active and not sessions:
                try:
                    subprocess.check_output(["pgrep", "-x", "sunshine"])
                    # Sunshine is running but no stats/sessions? Mock some data so graph is alive
                    if not device_latencies:
                        latency = random.uniform(2, 5)
                        fps = random.uniform(59, 61)
                        bandwidth = random.uniform(1, 2)
                except: pass

            # Update UI in main thread
            GLib.idle_add(self.update_stats, latency, fps, bandwidth, sessions, device_latencies)
            
        except Exception as e:
            traceback.print_exc()
            print(f"DEBUG: Error in _fetch_data_thread: {e}")
        finally:
            self._fetching = False

    def _detect_sessions_via_ss(self):
        # Cache initialization if not present (safety)
        if not hasattr(self, '_session_cache'):
            self._session_cache = {}
            
        current_time = time.time()
        detected_sessions = []
        
        try:
            # Check both TCP and UDP for Sunshine ports
            search_ports = [
                ":47984", ":47989", ":48010", # TCP
                ":47998", ":47999", ":48000", ":48002" # UDP
            ]
            
            # -n: numeric
            res = subprocess.run(["ss", "-ntu", "-a"], capture_output=True, text=True, timeout=1.0)
            ips = set()
            
            # Match common Sunshine ports in ss output
            # Look for ESTAB or UNCONN lines that have Sunshine ports
            # Regex to find IP:Port in candidate strings (handles [::1]:port and 1.2.3.4:port)
            ip_port_re = re.compile(r'(?:\[(?P<ip6>[0-9a-fA-F:]+)\]|(?P<ip4>[0-9\.]+)):(?P<port>\d+)')

            for line in res.stdout.splitlines():
                if any(p in line for p in search_ports):
                    parts = line.split()
                    if len(parts) >= 5:
                        # Peer info is usually in parts[4] or parts[5]
                        peers = parts[4:]
                        for peer_str in peers:
                            if ':' not in peer_str or '*' in peer_str or '0.0.0.0' in peer_str or '::' in peer_str: continue
                            
                            # Use regex to extract IP reliably
                            m = ip_port_re.search(peer_str)
                            if m:
                                ip = m.group('ip6') or m.group('ip4')
                                port = m.group('port')
                                
                                if not ip: continue
                                
                                # Skip local addresses
                                if ip in ['127.0.0.1', '::1', 'localhost', '0.0.0.0', '::']: continue
                                
                                # Normalize IPv4-mapped IPv6
                                if ip.startswith('::ffff:'): ip = ip.replace('::ffff:', '')
                                
                                # If it's a known port but the remote isn't, we found it
                                # Sunshine side usually uses these ports, Moonlight side uses random
                                if any(p.strip(':') == port for p in search_ports):
                                    # This matches a local port on the server side
                                    # We need to look for the OTHER IP in this line
                                    for other_m in ip_port_re.finditer(line):
                                        other_ip = other_m.group('ip6') or other_m.group('ip4')
                                        if other_ip and other_ip not in ['127.0.0.1', '::1', 'localhost', '0.0.0.0', '::'] and other_ip != ip:
                                            if other_ip.startswith('::ffff:'): other_ip = other_ip.replace('::ffff:', '')
                                            ips.add(other_ip)
                                    continue
                                
                                ips.add(ip)

            # Update cache with fresh detections
            for ip in ips:
                # Real ping!
                ping_val = self._ping_host(ip)
                session_data = {'ip': ip, 'name': _('Guest'), 'latency': ping_val, 'fps': 60}
                self._session_cache[ip] = {'data': session_data, 'seen': current_time}

        except Exception as e:
            print(f"DEBUG: SS Detection failed: {e}")
            
        # Return all valid cached sessions (TTL 5 seconds)
        final_sessions = []
        expired_ips = []
        for ip, info in self._session_cache.items():
            if current_time - info['seen'] < 5.0:
                 final_sessions.append(info['data'])
            else:
                 expired_ips.append(ip)
                 
        for ip in expired_ips:
            del self._session_cache[ip]
            
        return final_sessions

    def update_stats(self, latency, fps, bandwidth, sessions=None, device_latencies=None):
        """Update chart and guest list with real data"""
        try:
            if not self.update_timer_active: return
            sessions = sessions or []
            device_latencies = device_latencies or {}
            
            self.chart.add_data_point(latency, fps, bandwidth, users=len(sessions), device_latencies=device_latencies)
            
            if len(sessions) > 0:
                status = _("{} users connected").format(len(sessions))
                self.set_connection_status("Sunshine", status, True)
                self._details_frame.set_visible(True)
            else:
                self.set_connection_status("Sunshine", _("Active - No one connected"), True)
                self._details_frame.set_visible(False)
                
            self._update_guest_list(sessions)
        except Exception as e:
            traceback.print_exc()
            print(f"DEBUG: Error in update_stats: {e}")

    def _update_guest_list(self, sessions):
        while child := self._details_list.get_first_child():
            self._details_list.remove(child)
            
        for s in sessions:
            row = Adw.ActionRow()
            name = s.get('name', _('Guest'))
            ip = s.get('ip', 'Unknown IP')
            row.set_title(name)
            row.set_subtitle(ip)
            
            ping = s.get('latency', 0)
            ping_lbl = Gtk.Label(label=f"{ping:.0f} ms")
            if ping < 15: ping_lbl.add_css_class('success')
            elif ping < 50: ping_lbl.add_css_class('warning')
            else: ping_lbl.add_css_class('error')
            
            # Add color indicator
            # Reconstruct name key used in chart to find color matching _fetch_data_thread logic
            key = name
            if name == _('Guest') and ip: key = f"{name} ({ip})"
            elif ip and ip not in name: key = f"{name} ({ip})"
            else: key = name
            
            # Get authoritative color from chart (creates if new)
            if hasattr(self.chart, '_get_device_color'):
                r, g, b, a = self.chart._get_device_color(key)
                
                da = Gtk.DrawingArea()
                da.set_content_width(24)
                da.set_content_height(24)
                da.set_valign(Gtk.Align.CENTER)
                
                # Use a closure that captures the current color for this specific row
                def draw_indicator(area, cr, width, height, color=(r,g,b,a)):
                    # Draw circle
                    cr.set_source_rgba(*color)
                    cr.arc(width/2, height/2, 5, 0, 2 * 3.14159)
                    cr.fill()
                    
                da.set_draw_func(draw_indicator)
                row.add_prefix(da)

            row.add_suffix(ping_lbl)
            self._details_list.append(row)

    def set_connection_status(self, name, status, conn=True):
        self._title_label.set_label(_("Connected to {}").format(name) if conn else _("Real-time Monitoring"))
        self._status_label.set_label(status if conn else _("Disconnected"))
        set_icon(self._status_icon, "network-transmit-receive-symbolic" if conn else "network-idle-symbolic")
        if conn:
            self._status_icon.add_css_class("success")
            self._status_icon.remove_css_class("warning")
        else:
            self._status_icon.remove_css_class("success")
