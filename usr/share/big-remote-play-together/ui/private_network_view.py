import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Gdk
import subprocess
import threading
import os
import shutil
import time
import json
import re
from concurrent.futures import ThreadPoolExecutor
try:
    gi.require_version('Vte', '3.91')
    from gi.repository import Vte
    HAS_VTE = True
except:
    HAS_VTE = False
from utils.i18n import _
from utils.icons import create_icon_widget

class ProgressDots(Gtk.Box):
    """Progress indicator with dots - BigLinux Welcome Style"""
    def __init__(self, total):
        super().__init__(spacing=8)
        self.add_css_class("progress-container")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.dots = []
        for i in range(total):
            dot = Gtk.Box()
            dot.add_css_class("progress-dot")
            if i == 0: dot.add_css_class("active")
            self.dots.append(dot)
            self.append(dot)

    def set_page(self, page):
        for i, dot in enumerate(self.dots):
            dot.remove_css_class("active")
            dot.remove_css_class("completed")
            if i == page: dot.add_css_class("active")
            elif i < page: dot.add_css_class("completed")

class AccessInfoWidget(Gtk.Box):
    """Widget to display access information after installation"""
    def __init__(self, data, on_save_cb):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_top(20)
        self.set_margin_bottom(20)
        self.set_margin_start(20)
        self.set_margin_end(20)
        self.data = data
        self.on_save_cb = on_save_cb

        # Header
        title = Gtk.Label(label=_("Access Information"))
        title.add_css_class("title-1")
        self.append(title)

        # Content Group
        group = Adw.PreferencesGroup()
        self.append(group)

        # Fields mapping
        fields = [
            ("web_ui", _("Web Interface"), "external-link-symbolic"),
            ("api_url", _("API URL"), "network-server-symbolic"),
            ("public_ip", _("Public IP"), "network-workgroup-symbolic"),
            ("local_ip", _("Local IP"), "network-local-symbolic"),
            ("api_key", _("API Key (UI)"), "dialog-password-symbolic"),
            ("auth_key", _("Auth Key (Friends)"), "key-symbolic")
        ]

        for key, label, icon in fields:
            val = data.get(key, "")
            row = Adw.ActionRow(title=label, subtitle=val)
            row.add_prefix(create_icon_widget(icon, size=16))
            
            # Copy button
            btn_copy = Gtk.Button()
            btn_copy.set_child(create_icon_widget("edit-copy-symbolic", size=16))
            btn_copy.add_css_class("flat")
            btn_copy.set_valign(Gtk.Align.CENTER)
            btn_copy.connect("clicked", lambda b, v=val: self._copy_to_clipboard(v))
            row.add_suffix(btn_copy)

            # Open URL button for links
            if "http" in val:
                btn_open = Gtk.Button()
                btn_open.set_child(create_icon_widget("external-link-symbolic", size=16))
                btn_open.add_css_class("flat")
                btn_open.set_valign(Gtk.Align.CENTER)
                btn_open.connect("clicked", lambda b, v=val: os.system(f"xdg-open {v}"))
                row.add_suffix(btn_open)

            group.add(row)

        # Save Button
        self.btn_save = Gtk.Button(label=_("Save and Finish"))
        self.btn_save.add_css_class("suggested-action")
        self.btn_save.add_css_class("pill")
        self.btn_save.set_halign(Gtk.Align.CENTER)
        self.btn_save.set_margin_top(10)
        self.btn_save.connect("clicked", self.on_save_clicked)
        self.append(self.btn_save)

    def _copy_to_clipboard(self, text):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)

    def on_save_clicked(self, btn):
        self.on_save_cb(self.data)

class PrivateNetworkView(Adw.Bin):
    """View for managing private network (Headscale) with BigLinux Welcome aesthetic"""
    
    def __init__(self, main_window, mode='create'):
        super().__init__()
        self.main_window = main_window
        self.mode = mode
        self.public_ip = "..."
        self.dynamic_labels = [] # Labels to update with domain
        
        self._worker_running = False
        self._worker_thread = None
        self._ping_executor = ThreadPoolExecutor(max_workers=10)
        
        self.install_data = {}
        
        self.setup_ui()
        self.set_mode(mode)
        threading.Thread(target=self._fetch_public_ip, daemon=True).start()
        
    def setup_ui(self):
        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.set_child(self.main_stack)
        
        # Create Page (Wizard)
        self.create_page = self.setup_create_page()
        self.main_stack.add_named(self.create_page, 'create')
        
        # Connect Page
        self.connect_page = self.setup_connect_page()
        self.main_stack.add_named(self.connect_page, 'connect')
        
    def set_mode(self, mode):
        self.mode = mode
        self.main_stack.set_visible_child_name(mode)
        
        if mode == 'connect':
            self._start_worker()
        else:
            self._stop_worker()

        if mode == 'create':
            self.current_idx = 0
            self.create_stack.set_visible_child_name("step_0")
            self._update_nav()

    def setup_create_page(self):
        self.create_stack = Gtk.Stack()
        self.create_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.create_stack.set_transition_duration(320)
        
        # Steps
        self.page_widgets = []
        self.page_widgets.append(self.create_step_1_domain())
        self.page_widgets.append(self.create_step_2_cloudflare())
        self.page_widgets.append(self.create_step_3_api_setup())
        self.page_widgets.append(self.create_step_4_network())
        self.page_widgets.append(self.create_step_5_execution())
        
        for i, page in enumerate(self.page_widgets):
            self.create_stack.add_named(page, f"step_{i}")
        
        self.current_idx = 0

        # Custom Progress dots
        self.progress = ProgressDots(len(self.page_widgets))
        
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        
        # Bottom Navigation
        bottom_bar = Gtk.CenterBox()
        bottom_bar.add_css_class("bottom-bar")
        
        # Dots in center
        bottom_bar.set_center_widget(self.progress)
        
        # Buttons on the right (nav box)
        nav_box = Gtk.Box(spacing=10)
        
        self.btn_back = Gtk.Button()
        self.btn_back.set_child(create_icon_widget("go-previous-symbolic", size=16))
        self.btn_back.add_css_class("nav-button")
        self.btn_back.add_css_class("back")
        self.btn_back.set_visible(False)
        self.btn_back.connect("clicked", self.on_back_clicked)
        
        self.btn_next = Gtk.Button()
        # Initial state will be updated by _update_nav
        self.btn_next.connect("clicked", self.on_next_clicked)
        
        nav_box.append(self.btn_back)
        nav_box.append(self.btn_next)
        bottom_bar.set_end_widget(nav_box)
        
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self.create_stack)
        toolbar_view.add_bottom_bar(bottom_bar)
        
        self._update_nav()
        return toolbar_view

    def _update_nav(self):
        """Update navigation buttons and progress dots exactly like biglinux-welcome"""
        n_pages = len(self.page_widgets)
        
        # Update dots
        self.progress.set_page(self.current_idx)
        
        # Update Back button
        self.btn_back.set_visible(self.current_idx > 0)
        
        # Update Next button style
        is_last = (self.current_idx == n_pages - 1)
        if is_last:
            self.btn_next.remove_css_class("nav-button")
            self.btn_next.remove_css_class("next")
            self.btn_next.add_css_class("finish-button")
            self.btn_next.set_child(Gtk.Label(label=_("Install Server")))
        else:
            self.btn_next.add_css_class("nav-button")
            self.btn_next.add_css_class("next")
            self.btn_next.remove_css_class("finish-button")
            self.btn_next.set_child(create_icon_widget("go-next-symbolic", size=16))

    def create_step_1_domain(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = create_icon_widget("network-server-symbolic", size=32)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=_("1. Domain Registration"))
        title.add_css_class("title-3"); title.set_halign(Gtk.Align.START)
        desc = Gtk.Label(label=_("The first step is to have a domain pointed to Cloudflare."))
        desc.add_css_class("caption"); desc.add_css_class("dim-label"); desc.set_halign(Gtk.Align.START); desc.set_wrap(True)
        vbox.append(title); vbox.append(desc); header.append(icon); header.append(vbox)
        
        entry_group = Adw.PreferencesGroup(title=_("Enter your domain"))
        self.entry_domain = Adw.EntryRow(title=_("Domain Name"))
        entry_group.add(self.entry_domain)
        
        btn_site = Gtk.Button(label=_("Register Free Domain (DigitalPlat)"))
        btn_site.add_css_class("suggested-action"); btn_site.add_css_class("pill")
        btn_site.set_halign(Gtk.Align.CENTER)
        btn_site.connect("clicked", lambda b: os.system("xdg-open https://domain.digitalplat.org/"))
        
        box.append(header)
        box.append(entry_group)
        box.append(btn_site)
        return box

    def create_step_2_cloudflare(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)
        scroll.set_child(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = create_icon_widget("network-workgroup-symbolic", size=32)
        vbox_h = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title_h = Gtk.Label(label=_("2. Cloudflare Setup"))
        title_h.add_css_class("title-3"); title_h.set_halign(Gtk.Align.START)
        desc_h = Gtk.Label(label=_("Detailed tutorial to configure your domain"))
        desc_h.add_css_class("caption"); desc_h.add_css_class("dim-label"); desc_h.set_halign(Gtk.Align.START); desc_h.set_wrap(True)
        vbox_h.append(title_h); vbox_h.append(desc_h); header.append(icon); header.append(vbox_h)
        box.append(header)

        # 1. Account Creation
        g1 = Adw.PreferencesGroup(title=_("1. Access Cloudflare"))
        r1 = Adw.ActionRow(title=_("Create account and click '+ Add'"))
        b1 = Gtk.Button(label="dash.cloudflare.com")
        b1.add_css_class("pill"); b1.set_valign(Gtk.Align.CENTER)
        b1.connect("clicked", lambda b: os.system("xdg-open https://dash.cloudflare.com/"))
        r1.add_suffix(b1)
        g1.add(r1)
        box.append(g1)

        # 2. Add Domain
        g2 = Adw.PreferencesGroup(title=_("2. Enter Domain"))
        self.label_domain_info = Gtk.Label()
        self.label_domain_info.set_halign(Gtk.Align.START); self.label_domain_info.set_wrap(True)
        self.dynamic_labels.append(lambda d: self.label_domain_info.set_markup(_("Enter your domain: <b>{}</b>").format(d)))
        
        instructions = Gtk.Label(label=_("On the next page 'Speed up and secure your site':\n- Select: Quick DNS Check\n- Select: Global Block\n- Disable: AI Bots (robots.txt)\n- Click 'Continue'"))
        instructions.set_halign(Gtk.Align.START); instructions.add_css_class("caption"); instructions.add_css_class("dim-label")
        
        row_g2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        row_g2.append(self.label_domain_info); row_g2.append(instructions)
        g2.add(row_g2)
        box.append(g2)

        # 3. Choose Plan
        g3 = Adw.PreferencesGroup(title=_("3. Select Plan"))
        r3 = Adw.ActionRow(title=_("Choose the 'Free Plan' (first card) and click 'Select Plan'"))
        g3.add(r3)
        box.append(g3)

        # 4. DNS Records
        g4 = Adw.PreferencesGroup(title=_("4. DNS Records"))
        
        # Public IP Section
        ip_row = Adw.ActionRow(title=_("Your Public IP"))
        self.label_public_ip = Gtk.Label(label="...")
        btn_copy_ip = Gtk.Button()
        btn_copy_ip.set_child(create_icon_widget("edit-copy-symbolic", size=16))
        btn_copy_ip.add_css_class("flat"); btn_copy_ip.set_valign(Gtk.Align.CENTER)
        btn_copy_ip.connect("clicked", lambda b: self._copy_to_clipboard(self.public_ip))
        ip_row.add_suffix(self.label_public_ip)
        ip_row.add_suffix(btn_copy_ip)
        g4.add(ip_row)

        # TreeView for Records
        self.dns_store = Gtk.ListStore(str, str, str, str)
        self.dns_tree = Gtk.TreeView(model=self.dns_store)
        self.dns_tree.get_selection().set_mode(Gtk.SelectionMode.NONE)
        
        cols = [_("Type"), _("Name"), _("Target / IP"), _("Proxy")]
        for i, col_title in enumerate(cols):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(col_title, renderer, text=i)
            self.dns_tree.append_column(column)
            
        def update_dns_table(domain):
            self.dns_store.clear()
            self.dns_store.append(["A", "@", self.public_ip, _("Disabled (Gray)")])
            self.dns_store.append(["CNAME", "www", "@", _("-")])
        
        self.dynamic_labels.append(update_dns_table)
        
        tree_scroll = Gtk.ScrolledWindow(); tree_scroll.set_child(self.dns_tree)
        tree_scroll.set_min_content_height(100); tree_scroll.add_css_class("card")
        
        box_dns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box_dns.append(Gtk.Label(label=_("Click '+ Add Record' and fill as follows:"), halign=Gtk.Align.START))
        box_dns.append(tree_scroll)
        box_dns.append(Gtk.Label(label=_("After that, click 'Continue to activation'."), halign=Gtk.Align.START, css_classes=["caption", "dim-label"]))
        
        g4.add(box_dns)
        box.append(g4)

        # 5. Nameservers
        g5 = Adw.PreferencesGroup(title=_("5. Update Nameservers"))
        ins5 = Gtk.Label(label=_("- Replace your current NS with Cloudflare's NS1 and NS2\n- Update them in your registrar panel:"))
        ins5.set_halign(Gtk.Align.START); ins5.add_css_class("caption"); ins5.add_css_class("dim-label")
        
        btn_reg = Gtk.Button(label="dash.domain.digitalplat.org")
        btn_reg.add_css_class("pill"); btn_reg.set_halign(Gtk.Align.START)
        btn_reg.connect("clicked", lambda b: os.system("xdg-open https://dash.domain.digitalplat.org/panel/main?page=%2Fpanel%2Fdomains"))
        
        row_g5 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        row_g5.append(ins5); row_g5.append(btn_reg)
        g5.add(row_g5)
        box.append(g5)

        return scroll

    def create_step_3_api_setup(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)
        scroll.set_child(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = create_icon_widget("dialog-password-symbolic", size=32)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=_("3. Credentials"))
        title.add_css_class("title-3"); title.set_halign(Gtk.Align.START)
        desc = Gtk.Label(label=_("We need your Cloudflare API keys to automate DNS."))
        desc.add_css_class("caption"); desc.add_css_class("dim-label"); desc.set_halign(Gtk.Align.START); desc.set_wrap(True)
        vbox.append(title); vbox.append(desc); header.append(icon); header.append(vbox)
        box.append(header)

        # Tutorial for API Token
        tutorial_group = Adw.PreferencesGroup(title=_("How to generate your API Token"))
        self.label_token_tutorial = Gtk.Label()
        self.label_token_tutorial.set_halign(Gtk.Align.START); self.label_token_tutorial.set_wrap(True)
        self.label_token_tutorial.add_css_class("caption")
        
        def update_token_tutorial(domain):
            self.label_token_tutorial.set_markup(_(
                "<b>Cloudflare API Token (Edit DNS)</b>\n\n"
                "Para gerar esse API Token com a permissão específica de 'Edit DNS', siga este passo a passo:\n\n"
                "1. No painel da Cloudflare (Overview), procure <b>Get your API token</b> no canto inferior direito.\n"
                "2. Clique em <b>Create Token</b>.\n"
                "3. Use o primeiro modelo: <b>Edit zone DNS</b> (clique em Use template).\n"
                "4. Configure as permissões exatamente assim:\n"
                "   - Token name: <i>Script-Headscale</i>\n"
                "   - Permissions: <i>Zone - DNS - Edit</i>\n"
                "   - Zone Resources: Include - Specific zone - <b>{}</b>\n"
                "5. Clique em <b>Continue to summary</b> e depois <b>Create Token</b>.\n\n"
                "<b>Atenção:</b> O Token aparecerá apenas uma vez. Copie e guarde-o bem!"
            ).format(domain or "..."))
            
        self.dynamic_labels.append(update_token_tutorial)
        tutorial_group.add(self.label_token_tutorial)
        box.append(tutorial_group)
        
        group = Adw.PreferencesGroup(title=_("API Access"))
        self.entry_zone = Adw.EntryRow(title="Zone ID")
        self.entry_token = Adw.PasswordEntryRow(title="API Token (Edit DNS)")
        group.add(self.entry_zone)
        group.add(self.entry_token)
        box.append(group)
        
        info_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_card.add_css_class("info-card")
        info_text = Gtk.Label(label=_("Zone ID is in the 'Overview' page. Token must have 'Zone.DNS' edit permissions."))
        info_text.set_wrap(True)
        info_text.add_css_class("caption")
        info_card.append(info_text)
        box.append(info_card)
        
        return scroll

    def create_step_4_network(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = create_icon_widget("network-transmit-receive-symbolic", size=32)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=_("4. Network & Ports"))
        title.add_css_class("title-3"); title.set_halign(Gtk.Align.START)
        desc = Gtk.Label(label=_("Ensure your router is ready"))
        desc.add_css_class("caption"); desc.add_css_class("dim-label"); desc.set_halign(Gtk.Align.START); desc.set_wrap(True)
        vbox.append(title); vbox.append(desc); header.append(icon); header.append(vbox)
        
        ports_group = Adw.PreferencesGroup(title=_("Required Port Forwarding"))
        ports = [
            ("8080 TCP", _("Web and API")),
            ("9443 TCP", _("Admin Panel")),
            ("41641 UDP", _("Peer-to-peer data"))
        ]
        
        for p, desc in ports:
            row = Adw.ActionRow(title=p, subtitle=desc)
            ports_group.add(row)
            
        warning = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        warning.add_css_class("info-card")
        warn_icon = create_icon_widget("dialog-warning-symbolic")
        warn_label = Gtk.Label(label=_("Cloudflare Proxy (Orange Cloud) MUST be DISABLED (Gray)."))
        warn_label.set_wrap(True)
        warning.append(warn_icon)
        warning.append(warn_label)

        box.append(header)
        box.append(ports_group)
        box.append(warning)
        return box

    def create_step_5_execution(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = create_icon_widget("preferences-system-symbolic", size=32)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=_("5. Installation"))
        title.add_css_class("title-3"); title.set_halign(Gtk.Align.START)
        desc = Gtk.Label(label=_("Setting up Docker, Headscale and Caddy..."))
        desc.add_css_class("caption"); desc.add_css_class("dim-label"); desc.set_halign(Gtk.Align.START); desc.set_wrap(True)
        vbox.append(title); vbox.append(desc); header.append(icon); header.append(vbox)

        self.exec_label = Gtk.Label(label=_("Ready to Begin"))
        self.exec_label.add_css_class("title-4")
        self.exec_label.set_halign(Gtk.Align.START)
        
        self.text_view = Gtk.TextView(editable=False, monospace=True)
        self.text_view.add_css_class("card")
        self.text_view.set_size_request(-1, 250)
        self.text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        
        # Setup tags for ANSI colors
        buffer = self.text_view.get_buffer()
        table = buffer.get_tag_table()
        ansi_colors = {
            "green": "#2ec27e",
            "blue": "#3584e4",
            "yellow": "#f5c211",
            "red": "#ed333b",
            "cyan": "#33c7de",
            "bold": None
        }
        for name, color in ansi_colors.items():
            tag = Gtk.TextTag(name=name)
            if color: tag.set_property("foreground", color)
            if name == "bold": tag.set_property("weight", 700)
            table.add(tag)
        
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.text_view)
        scroll.add_css_class("card")
        
        box.append(header)
        box.append(self.exec_label)
        box.append(scroll)
        return box

    def setup_connect_page(self):
        self.connect_toolbar_view = Adw.ToolbarView()
        self.connect_stack = Adw.ViewStack()
        
        # 1. Connection Form Tab

        # 2. Connection Form Tab
        conn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        conn_box.set_margin_top(30); conn_box.set_margin_bottom(30); conn_box.set_margin_start(40); conn_box.set_margin_end(40)
        
        status = Adw.StatusPage(
            title=_("Connect to Network"), 
            icon_name="network-vpn-symbolic",
            description=_("Join an existing Headscale private network")
        )
        conn_box.append(status)
        
        group = Adw.PreferencesGroup()
        self.entry_connect_domain = Adw.EntryRow(title=_("Server Domain"))
        self.entry_auth_key = Adw.PasswordEntryRow(title=_("Auth Key"))
        
        # Load saved values
        app = self.main_window.get_application()
        if hasattr(app, 'config'):
            saved_domain = app.config.get('private_network_domain', '')
            saved_key = app.config.get('private_network_key', '')
            self.entry_connect_domain.set_text(saved_domain)
            self.entry_auth_key.set_text(saved_key)
            
        # Connect signals to save on change
        self.entry_connect_domain.connect("changed", self._on_domain_changed)
        self.entry_auth_key.connect("changed", self._on_key_changed)
        
        group.add(self.entry_connect_domain)
        group.add(self.entry_auth_key)
        conn_box.append(group)
        
        btn_connect = Gtk.Button(label=_("Establish Connection"))
        btn_connect.add_css_class("suggested-action")
        btn_connect.add_css_class("pill")
        btn_connect.set_halign(Gtk.Align.CENTER)
        btn_connect.set_size_request(200, -1)
        btn_connect.connect("clicked", self.on_connect_clicked)
        conn_box.append(btn_connect)
        
        self.connect_log = Gtk.TextView(editable=False, monospace=True, vexpand=True)
        self.connect_log.add_css_class("card")
        scroll_log = Gtk.ScrolledWindow(vexpand=True); scroll_log.set_child(self.connect_log)
        conn_box.append(scroll_log)
        
        page_conn = self.connect_stack.add_titled(conn_box, "connection", _("Connect"))
        page_conn.set_icon_name("network-server-symbolic")

        # 3. Network Status Tab
        net_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        net_box.set_margin_top(12); net_box.set_margin_bottom(12); net_box.set_margin_start(12); net_box.set_margin_end(12)
        
        net_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        net_title = Gtk.Label(label=_("Network Devices"))
        net_title.add_css_class("title-4")
        net_header.append(net_title)
        
        btn_refresh = Gtk.Button()
        btn_refresh.set_child(create_icon_widget("view-refresh-symbolic", size=16))
        btn_refresh.add_css_class("flat")
        btn_refresh.connect("clicked", lambda b: self.refresh_peers())
        btn_refresh.set_halign(Gtk.Align.END); btn_refresh.set_hexpand(True)
        net_header.append(btn_refresh)
        net_box.append(net_header)

        # Columns: IP, Host, User, OS, Connection/Relay, Stats (Tx/Rx), Ping
        self.peers_model = Gtk.ListStore(str, str, str, str, str, str, str)
        self.peers_tree = Gtk.TreeView(model=self.peers_model)
        
        cols = [_("IP"), _("Host"), _("User"), _("System"), _("Connection"), _("Traffic (Tx/Rx)"), _("Ping")]
        for i, col_title in enumerate(cols):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(col_title, renderer, text=i)
            if i == 6: renderer.set_property("xalign", 0.5)
            column.set_resizable(True)
            # Expand Host and Connection
            column.set_expand(True if i in [1, 4] else False)
            self.peers_tree.append_column(column)
        
        scroll_tree = Gtk.ScrolledWindow(vexpand=True); scroll_tree.set_child(self.peers_tree)
        scroll_tree.add_css_class("card")
        net_box.append(scroll_tree)
        
        page_net = self.connect_stack.add_titled(net_box, "network", _("Status"))
        page_net.set_icon_name("network-transmit-receive-symbolic")

        # 3. Previous Networks Tab (Now Last)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.history_box.set_margin_top(30); self.history_box.set_margin_bottom(30); self.history_box.set_margin_start(40); self.history_box.set_margin_end(40)
        
        history_scroll = Gtk.ScrolledWindow(vexpand=True)
        self.history_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        history_scroll.set_child(self.history_list_box)
        self.history_box.append(history_scroll)
        
        page_hist = self.connect_stack.add_titled(self.history_box, "history", _("Previous Networks"))
        page_hist.set_icon_name("document-open-recent-symbolic")
        
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        switcher = Adw.ViewSwitcher(stack=self.connect_stack)
        header.set_title_widget(switcher)
        self.connect_toolbar_view.add_top_bar(header)
        self.connect_toolbar_view.set_content(self.connect_stack)
        
        self.connect_stack.connect("notify::visible-child-name", self.on_connect_stack_changed)
        
        if self.mode == 'connect': 
            self._start_worker()
            self.refresh_history_ui()

        return self.connect_toolbar_view

    def refresh_history_ui(self):
        """Load history from JSON and populate the list box"""
        # Clear current list
        while child := self.history_list_box.get_first_child():
            self.history_list_box.remove(child)
        
        config_dir = os.path.expanduser("~/.config/big-remoteplay/private_network")
        history_file = os.path.join(config_dir, "private_network.json")
        
        if not os.path.exists(history_file):
            status = Adw.StatusPage(
                title=_("No History"),
                icon_name="document-open-recent-symbolic",
                description=_("Your created networks will appear here.")
            )
            self.history_list_box.append(status)
            return

        try:
            with open(history_file, 'r') as f:
                data = json.load(f)
                history = data.get("history", [])
        except:
            history = []

        if not history:
            status = Adw.StatusPage(
                title=_("History is Empty"),
                icon_name="document-open-recent-symbolic"
            )
            self.history_list_box.append(status)
            return

        for entry in reversed(history):
            raw_url = entry.get('api_url') or entry.get('web_ui', '')
            clean_domain = raw_url.replace('http://', '').replace('https://', '').strip('/')
            entry_id = entry.get('id', '?')
            timestamp = entry.get('timestamp', '')

            group = Adw.PreferencesGroup()
            group.set_title(f"ID: {entry_id} - {clean_domain}")
            group.set_description(timestamp)
            
            # Management Buttons in the Header Suffix
            header_box = Gtk.Box(spacing=6)
            
            # 1. Reconnect
            btn_reconnect = Gtk.Button()
            btn_reconnect.set_child(create_icon_widget("network-vpn-symbolic", size=16, css_class=["blue-icon"]))
            btn_reconnect.add_css_class("flat")
            btn_reconnect.add_css_class("suggested-action")
            btn_reconnect.set_tooltip_text(_("Reconnect"))
            btn_reconnect.connect("clicked", lambda b, e=entry: self.reconnect_from_history(e))
            header_box.append(btn_reconnect)
            
            # 2. Save TXT
            btn_save = Gtk.Button()
            btn_save.set_child(create_icon_widget("document-save-symbolic", size=16))
            btn_save.add_css_class("flat")
            btn_save.set_tooltip_text(_("Save to TXT"))
            btn_save.connect("clicked", lambda b, e=entry: self.save_entry_to_txt(e))
            header_box.append(btn_save)
            
            # 3. Delete
            btn_delete = Gtk.Button()
            btn_delete.set_child(create_icon_widget("user-trash-symbolic", size=16))
            btn_delete.add_css_class("flat")
            btn_delete.add_css_class("destructive-action")
            btn_delete.set_tooltip_text(_("Delete from history"))
            btn_delete.connect("clicked", lambda b, e=entry: self.confirm_delete_history(e))
            header_box.append(btn_delete)
            
            # Set suffix to the group header
            group.set_header_suffix(header_box)

            # Rows inside the group
            # 1. Domain Row
            domain_row = Adw.ActionRow(title=_("Domain"), subtitle=clean_domain)
            domain_row.add_prefix(create_icon_widget("network-server-symbolic", size=16))
            
            btn_copy_dom = Gtk.Button()
            btn_copy_dom.set_child(create_icon_widget("edit-copy-symbolic", size=16))
            btn_copy_dom.add_css_class("flat")
            btn_copy_dom.set_tooltip_text(_("Copy Domain"))
            btn_copy_dom.connect("clicked", lambda b, v=clean_domain: self._copy_to_clipboard(v))
            domain_row.add_suffix(btn_copy_dom)
            group.add(domain_row)

            # Masked row helper
            def add_masked_row(grp, title, value, icon):
                masked_val = "••••••••••••••••"
                row = Adw.ActionRow(title=title, subtitle=masked_val)
                row.add_prefix(create_icon_widget(icon, size=16))

                # Visibility Button
                btn_view = Gtk.Button()
                btn_view.set_child(create_icon_widget("view-reveal-symbolic", size=16))
                btn_view.add_css_class("flat")
                btn_view.set_valign(Gtk.Align.CENTER)
                
                def toggle_view(btn, r, val):
                    is_masked = r.get_subtitle() == "••••••••••••••••"
                    r.set_subtitle(val if is_masked else "••••••••••••••••")
                    btn.set_child(create_icon_widget("view-reveal-symbolic" if not is_masked else "view-conceal-symbolic", size=16))
                
                btn_view.connect("clicked", toggle_view, row, value)
                row.add_suffix(btn_view)

                # Copy Button
                btn_copy = Gtk.Button()
                btn_copy.set_child(create_icon_widget("edit-copy-symbolic", size=16))
                btn_copy.add_css_class("flat")
                btn_copy.set_valign(Gtk.Align.CENTER)
                btn_copy.connect("clicked", lambda b, v=value: self._copy_to_clipboard(v))
                row.add_suffix(btn_copy)
                
                grp.add(row)

            # Add rows with icons matching Server Information style
            add_masked_row(group, _("API Key"), entry.get('api_key', ''), "dialog-password-symbolic")
            add_masked_row(group, _("Auth Key (Friends)"), entry.get('auth_key', ''), "key-symbolic")
            
            self.history_list_box.append(group)
            
            self.history_list_box.append(group)

    def reconnect_from_history(self, entry):
        """Auto-fill connection form and trigger connection"""
        domain = entry.get('api_url', '').replace('http://', '').replace('https://', '').split('/')[0]
        auth_key = entry.get('auth_key', '')
        
        if not domain or not auth_key:
            self.main_window.show_toast(_("Incomplete data in history"))
            return
            
        self.entry_connect_domain.set_text(domain)
        self.entry_auth_key.set_text(auth_key)
        self.connect_stack.set_visible_child_name("connection")
        self.on_connect_clicked(None)

    def save_entry_to_txt(self, entry):
        """Save access info to a .txt file for sharing"""
        dialog = Gtk.FileDialog(title=_("Save Network Information"))
        dialog.set_initial_name(f"network_info_{entry.get('id')}.txt")
        
        def on_save_response(dialog, result):
            try:
                file = dialog.save_finish(result)
                if file:
                    path = file.get_path()
                    content = (
                        f"INFORMACOES DE ACESSO (ID: {entry.get('id')})\n"
                        f"Data: {entry.get('timestamp')}\n"
                        f"-----------------------------------\n"
                        f"Interface Web: {entry.get('web_ui')}\n"
                        f"URL da API: {entry.get('api_url')}\n"
                        f"IP Publico: {entry.get('public_ip')}\n"
                        f"IP Local: {entry.get('local_ip')}\n\n"
                        f"CREDENCIAIS\n"
                        f"API Key: {entry.get('api_key')}\n"
                        f"Chave Amigos: {entry.get('auth_key')}\n"
                    )
                    with open(path, 'w') as f:
                        f.write(content)
                    self.main_window.show_toast(_("File saved!"))
            except Exception as e:
                self.main_window.show_toast(_("Error saving: {}").format(e))

        dialog.save(self.main_window, None, on_save_response)

    def confirm_delete_history(self, entry):
        """Confirm before removing history entry"""
        dialog = Adw.MessageDialog(
            transient_for=self.main_window,
            heading=_("Delete History?"),
            body=_("Are you sure you want to remove ID {} from history?").format(entry.get('id'))
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(dlg, response):
            if response == "delete":
                self.delete_history_id(entry.get('id'))
        
        dialog.connect("response", on_response)
        dialog.present()

    def delete_history_id(self, entry_id):
        """Remove entry from JSON history"""
        config_dir = os.path.expanduser("~/.config/big-remoteplay/private_network")
        history_file = os.path.join(config_dir, "private_network.json")
        
        try:
            with open(history_file, 'r') as f:
                data = json.load(f)
                history = data.get("history", [])
            
            new_history = [e for e in history if e.get('id') != entry_id]
            
            with open(history_file, 'w') as f:
                json.dump({"history": new_history}, f, indent=4)
            
            self.refresh_history_ui()
            self.main_window.show_toast(_("Deleted from history"))
        except Exception as e:
            self.main_window.show_toast(_("Error deleting: {}").format(e))

    def on_connect_stack_changed(self, stack, param):
        name = stack.get_visible_child_name()
        if name == "network":
            self.refresh_peers()
        elif name == "history":
            self.refresh_history_ui()

    def _on_domain_changed(self, entry):
        domain = entry.get_text()
        for update_fn in self.dynamic_labels:
            update_fn(domain)
        app = self.main_window.get_application()
        if hasattr(app, 'config'):
            app.config.set('private_network_domain', domain)

    def _fetch_public_ip(self):
        try:
            ip = subprocess.check_output(["curl", "-s", "ipinfo.io/ip"]).decode().strip()
            self.public_ip = ip
            GLib.idle_add(self.label_public_ip.set_label, ip)
            # Refresh DNS table with the real IP
            domain = self.entry_domain.get_text()
            GLib.idle_add(lambda: [f(domain) for f in self.dynamic_labels])
        except:
            self.public_ip = "Error"
            GLib.idle_add(self.label_public_ip.set_label, "Error")

    def _copy_to_clipboard(self, text):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)
        self.main_window.show_toast(_("Copied: {}").format(text))

    def _on_key_changed(self, entry):
        app = self.main_window.get_application()
        if hasattr(app, 'config'):
            app.config.set('private_network_key', entry.get_text())

    def _start_worker(self):
        if self._worker_running: return
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._status_worker, daemon=True)
        self._worker_thread.start()

    def _stop_worker(self):
        self._worker_running = False

    def _status_worker(self):
        while self._worker_running:
            if self.mode == 'connect':
                # Only refresh if the network tab is visible to save resources
                if hasattr(self, 'connect_stack') and self.connect_stack.get_visible_child_name() == "network":
                    self._get_tailscale_status()
            
            # Refresh cycle
            for _ in range(30): # 3 seconds total
                if not self._worker_running: break
                time.sleep(0.1)

    def refresh_peers(self):
        threading.Thread(target=self._get_tailscale_status, daemon=True).start()
        return True

    def _get_tailscale_status(self):
        if hasattr(self, '_fetching_status') and self._fetching_status: return
        self._fetching_status = True
        
        try:
            ts_path = shutil.which("tailscale") or "/usr/bin/tailscale"
            if not os.path.exists(ts_path):
                self._fetching_status = False
                return
            
            result = subprocess.run([ts_path, "status"], capture_output=True, text=True)
            if result.returncode != 0:
                self._fetching_status = False
                return
            
            nodes = []
            for line in result.stdout.splitlines():
                if not line or line.startswith('IP'): continue
                
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    host = parts[1]
                    user = parts[2]
                    os_sys = parts[3]
                    status_raw = " ".join(parts[4:]) if len(parts) > 4 else "-"
                    
                    # Connection parsing logic inspired by user script
                    conn_type = "inactive"
                    conn_detail = "-"
                    online_status = "offline"
                    
                    if "active" in status_raw.lower():
                        online_status = "online"
                    if "offline" in status_raw.lower():
                        online_status = "offline"
                        
                    if "direct" in status_raw.lower():
                        conn_type = "direct"
                        match_addr = re.search(r'direct ([\d\.:]*)', status_raw)
                        conn_detail = match_addr.group(1) if match_addr else "direct"
                    elif "relay" in status_raw.lower():
                        conn_type = "relay"
                        match_relay = re.search(r'relay "([^"]*)"', status_raw)
                        conn_detail = match_relay.group(1) if match_relay else "relay"
                    
                    # Extract TX/RX
                    tx_match = re.search(r'tx (\d+)', status_raw)
                    rx_match = re.search(r'rx (\d+)', status_raw)
                    tx = tx_match.group(1) if tx_match else "0"
                    rx = rx_match.group(1) if rx_match else "0"
                    
                    traffic = f"↑{tx} ↓{rx}"
                    connection = f"{online_status} ({conn_type}: {conn_detail})"
                    
                    nodes.append({
                        'ip': ip,
                        'host': host,
                        'user': user,
                        'os': os_sys,
                        'connection': connection,
                        'traffic': traffic,
                        'ping': "..."
                    })

            # Update UI immediately
            ui_data = []
            for n in nodes:
                ui_data.append((n['ip'], n['host'], n['user'], n['os'], n['connection'], n['traffic'], n['ping']))
            
            GLib.idle_add(self._update_peers_ui, ui_data)

            # Parallel Pings
            def do_ping_and_update(idx, node):
                ip = node['ip']
                if not ip or ip == '-': return
                
                ping_val = "-"
                try:
                    res = subprocess.run(["ping", "-c", "2", "-W", "1", "-n", ip], capture_output=True, text=True)
                    if res.returncode == 0:
                        # Extract average RTT
                        summary_match = re.search(r'min/avg/max/mdev\s*=\s*[\d.]+/([\d.]+)/', res.stdout)
                        if summary_match:
                            ping_val = f"{summary_match.group(1)} ms"
                        else:
                            time_match = re.search(r'time=([\d.,]+)\s*ms', res.stdout)
                            if time_match:
                                ping_val = f"{time_match.group(1).replace(',', '.')} ms"
                except: pass
                
                GLib.idle_add(self._update_single_ping, idx, ping_val)

            for i, node in enumerate(nodes):
                self._ping_executor.submit(do_ping_and_update, i, node)

        except: pass
        finally:
            self._fetching_status = False

    def _update_single_ping(self, idx, ping_val):
        try:
            if idx < self.peers_model.iter_n_children():
                it = self.peers_model.get_iter_from_string(str(idx))
                if it:
                    # Column index for Ping is now 6
                    self.peers_model.set_value(it, 6, ping_val)
        except: pass

    def _update_peers_ui(self, peers):
        self.peers_model.clear()
        for p in peers: self.peers_model.append(p)

    def on_next_clicked(self, button):
        n_pages = len(self.page_widgets)
        
        if self.current_idx == 0:
            if not self.entry_domain.get_text():
                self.main_window.show_toast(_("Domain is required"))
                return
        elif self.current_idx == 2:
            if not self.entry_zone.get_text() or not self.entry_token.get_text():
                self.main_window.show_toast(_("API Keys are required"))
                return
        
        if self.current_idx < n_pages - 1:
            self.current_idx += 1
            self.create_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
            self.create_stack.set_visible_child_name(f"step_{self.current_idx}")
            self._update_nav()
        else:
            self.run_install()

    def on_back_clicked(self, button):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.create_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
            self.create_stack.set_visible_child_name(f"step_{self.current_idx}")
            self._update_nav()

    def log(self, text, view=None):
        if view is None: view = self.text_view
        GLib.idle_add(self._log_idle, text, view)

    def _apply_ansi_tags(self, buffer, text):
        ansi_escape = re.compile(r'(\x1b\[[0-9;]*[mK])')
        parts = ansi_escape.split(text)
        
        current_tags = []
        for part in parts:
            if part.startswith('\x1b['):
                if part == '\x1b[0m':
                    current_tags = []
                elif '0;32' in part: current_tags = ["green"]
                elif '0;34' in part: current_tags = ["blue"]
                elif '1;33' in part: current_tags = ["yellow"]
                elif '0;31' in part: current_tags = ["red"]
                elif '0;36' in part: current_tags = ["cyan"]
                elif '1;' in part: current_tags.append("bold")
            else:
                if part:
                    buffer.insert_with_tags_by_name(buffer.get_end_iter(), part, *current_tags)

    def _log_idle(self, text, view):
        buf = view.get_buffer()
        self._apply_ansi_tags(buf, text + "\n")
        mark = buf.get_insert(); view.scroll_to_mark(mark, 0.0, True, 0.5, 1.0)

    def run_install(self):
        self.btn_next.set_sensitive(False)
        self.exec_label.set_text(_("Installing..."))
        self.text_view.get_buffer().set_text("")
        domain = self.entry_domain.get_text(); zone = self.entry_zone.get_text(); token = self.entry_token.get_text()
        
        def thread_func():
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script_path = os.path.join(base_dir, "scripts", "create-network_headscale.sh")
            if not os.path.exists(script_path): script_path = "/usr/share/big-remote-play-together/scripts/create-network_headscale.sh"
            
            cmd = ["bigsudo", script_path]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            inputs = ["1\n", f"{domain}\n", f"{zone}\n", f"{token}\n", "n\n"]
            for s in inputs:
                process.stdin.write(s); process.stdin.flush()
            
            self.install_data = {}
            while True:
                line = process.stdout.readline()
                if not line: break
                clean_line = re.sub(r'\x1b\[[0-9;]*[mK]', '', line).strip()
                
                # Capture information
                if "Interface Web:" in clean_line: self.install_data["web_ui"] = clean_line.split("Interface Web:")[1].strip()
                elif "URL da API:" in clean_line: self.install_data["api_url"] = clean_line.split("URL da API:")[1].strip()
                elif "Seu IP Público:" in clean_line: self.install_data["public_ip"] = clean_line.split("Seu IP Público:")[1].strip()
                elif "IP Local do Servidor:" in clean_line: self.install_data["local_ip"] = clean_line.split("IP Local do Servidor:")[1].strip()
                elif "API Key (para UI):" in clean_line: self.install_data["api_key"] = clean_line.split("API Key (para UI):")[1].strip()
                elif "Chave para Amigos:" in clean_line: self.install_data["auth_key"] = clean_line.split("Chave para Amigos:")[1].strip()

                self.log(line.strip())
            process.wait()
            GLib.idle_add(self.on_install_finished, process.returncode)
        threading.Thread(target=thread_func, daemon=True).start()

    def on_install_finished(self, code):
        self.exec_label.set_text(_("Finished with code: {}").format(code))
        if code == 0: 
            self.main_window.show_toast(_("Success!"))
            self.show_success_dialog()
        else: 
            self.main_window.show_toast(_("Installation failed"))
        self.btn_next.set_sensitive(True); self.btn_next.set_label(_("Try Again"))

    def show_success_dialog(self):
        """Show the access information dialog"""
        content = AccessInfoWidget(self.install_data, self.save_history)
        
        # Check for Adw.Dialog (Libadwaita 1.5+)
        if hasattr(Adw, 'Dialog'):
            dialog = Adw.Dialog()
            dialog.set_child(content)
            dialog.set_title(_("Network Established"))
            dialog.present(self.main_window)
            self.current_dialog = dialog
        else:
            # Fallback to Adw.Window styled as a dialog
            dialog = Adw.Window(transient_for=self.main_window)
            dialog.set_modal(True)
            dialog.set_title(_("Network Established"))
            dialog.set_default_size(500, -1)
            
            # Use a ToolbarView to look like a dialog
            tv = Adw.ToolbarView()
            hb = Adw.HeaderBar()
            tv.add_top_bar(hb)
            tv.set_content(content)
            dialog.set_content(tv)
            dialog.present()
            self.current_dialog = dialog

    def save_history(self, data):
        """Save installation to private_network.json"""
        if hasattr(self, 'current_dialog'):
            if hasattr(self.current_dialog, 'close'): self.current_dialog.close()
            else: self.current_dialog.destroy()

        config_dir = os.path.expanduser("~/.config/big-remoteplay/private_network")
        os.makedirs(config_dir, exist_ok=True)
        history_file = os.path.join(config_dir, "private_network.json")
        
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    content = json.load(f)
                    history = content.get("history", [])
            except: pass
        
        # Generate sequential ID
        new_id = 1
        if history:
            ids = [h.get("id", 0) for h in history]
            new_id = max(ids) + 1
        
        entry = data.copy()
        entry["id"] = new_id
        entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        history.append(entry)
        
        try:
            with open(history_file, 'w') as f:
                json.dump({"history": history}, f, indent=4)
            self.main_window.show_toast(_("Configuration saved to history"))
            self.refresh_history_ui()
        except Exception as e:
            self.main_window.show_toast(_("Error saving history: {}").format(e))

    def on_connect_clicked(self, btn):
        domain = self.entry_connect_domain.get_text(); key = self.entry_auth_key.get_text()
        if not domain or not key:
            self.main_window.show_toast(_("Fill all fields"))
            return
        btn.set_sensitive(False); self.connect_log.get_buffer().set_text("")
        def thread_func():
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            script_path = os.path.join(base_dir, "scripts", "create-network_headscale.sh")
            if not os.path.exists(script_path): script_path = "/usr/share/big-remote-play-together/scripts/create-network_headscale.sh"
            cmd = ["bigsudo", script_path]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            inputs = ["2\n", f"{domain}\n", f"{key}\n", "n\n"]
            for s in inputs:
                process.stdin.write(s); process.stdin.flush()
            while True:
                line = process.stdout.readline()
                if not line: break
                self.log(line.strip(), view=self.connect_log)
            process.wait()
            GLib.idle_add(lambda: btn.set_sensitive(True))
        threading.Thread(target=thread_func, daemon=True).start()
