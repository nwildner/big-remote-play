import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
import subprocess
import threading
import os
import shutil
from utils.i18n import _

class PrivateNetworkView(Adw.Bin):
    """View for managing private network (Headscale) with BigLinux Welcome aesthetic"""
    
    def __init__(self, main_window, mode='create'):
        super().__init__()
        self.main_window = main_window
        self.mode = mode
        self.public_ip = "..."
        self.dynamic_labels = [] # Labels to update with domain
        
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
        if mode == 'create':
            # Reset create wizard to first page
            if hasattr(self, 'create_carousel') and self.create_carousel.get_n_pages() > 0:
                first_page = self.create_carousel.get_nth_page(0)
                self.create_carousel.scroll_to(first_page, False)
                self.btn_next.set_label(_("Next"))
                self.btn_next.set_sensitive(True)
                self.btn_back.set_sensitive(False)

    def setup_create_page(self):
        self.create_carousel = Adw.Carousel()
        self.create_carousel.set_interactive(False) # Force navigation via buttons
        
        # Steps
        self.create_step_1_domain()
        self.create_step_2_cloudflare()
        self.create_step_3_api_setup()
        self.create_step_4_network()
        self.create_step_5_execution()
        
        # Dots Indicator for Header
        self.dots = Adw.CarouselIndicatorDots()
        self.dots.set_carousel(self.create_carousel)
        self.dots.set_margin_top(10)
        self.dots.set_margin_bottom(10)
        
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        header.set_title_widget(self.dots)
        
        # Content Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Bottom Navigation
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        bottom_bar.set_margin_top(18)
        bottom_bar.set_margin_bottom(24)
        bottom_bar.set_margin_start(24)
        bottom_bar.set_margin_end(24)
        bottom_bar.set_halign(Gtk.Align.CENTER)
        bottom_bar.add_css_class("bottom-bar")
        
        self.btn_back = Gtk.Button(label=_("Back"))
        self.btn_back.add_css_class("pill")
        self.btn_back.set_sensitive(False)
        self.btn_back.set_size_request(120, -1)
        self.btn_back.connect("clicked", self.on_back_clicked)
        
        self.btn_next = Gtk.Button(label=_("Next"))
        self.btn_next.add_css_class("suggested-action")
        self.btn_next.add_css_class("pill")
        self.btn_next.set_size_request(120, -1)
        self.btn_next.connect("clicked", self.on_next_clicked)
        
        bottom_bar.append(self.btn_back)
        bottom_bar.append(self.btn_next)
        
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self.create_carousel)
        toolbar_view.add_bottom_bar(bottom_bar)
        
        return toolbar_view

    def create_step_1_domain(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("network-server-symbolic")
        icon.set_pixel_size(32)
        
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
        self.create_carousel.append(box)

    def create_step_2_cloudflare(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)
        scroll.set_child(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("cloud-symbolic")
        icon.set_pixel_size(32)
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
        btn_copy_ip = Gtk.Button(icon_name="edit-copy-symbolic")
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

        self.create_carousel.append(scroll)

    def create_step_3_api_setup(self):
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)
        scroll.set_child(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        icon.set_pixel_size(32)
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
        
        self.create_carousel.append(scroll)

    def create_step_4_network(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("network-transmit-receive-symbolic")
        icon.set_pixel_size(32)
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
        warn_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        warn_label = Gtk.Label(label=_("Cloudflare Proxy (Orange Cloud) MUST be DISABLED (Gray)."))
        warn_label.set_wrap(True)
        warning.append(warn_icon)
        warning.append(warn_label)

        box.append(header)
        box.append(ports_group)
        box.append(warning)
        self.create_carousel.append(box)

    def create_step_5_execution(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(30); box.set_margin_bottom(30); box.set_margin_start(40); box.set_margin_end(40)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("system-run-symbolic")
        icon.set_pixel_size(32)
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
        self.text_view.set_size_request(-1, 200)
        
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.text_view)
        scroll.add_css_class("card")
        
        box.append(header)
        box.append(self.exec_label)
        box.append(scroll)
        self.create_carousel.append(box)

    def setup_connect_page(self):
        self.connect_toolbar_view = Adw.ToolbarView()
        self.connect_stack = Adw.ViewStack()
        
        # 1. Connection Form Tab
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
        
        self.connect_stack.add_titled(conn_box, "connection", _("Connect"))

        # 2. Network Status Tab
        net_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        net_box.set_margin_top(12); net_box.set_margin_bottom(12); net_box.set_margin_start(12); net_box.set_margin_end(12)
        
        net_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        net_title = Gtk.Label(label=_("Network Devices"))
        net_title.add_css_class("title-4")
        net_header.append(net_title)
        
        btn_refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        btn_refresh.add_css_class("flat")
        btn_refresh.connect("clicked", lambda b: self.refresh_peers())
        btn_refresh.set_halign(Gtk.Align.END); btn_refresh.set_hexpand(True)
        net_header.append(btn_refresh)
        net_box.append(net_header)

        self.peers_model = Gtk.ListStore(str, str, str, str, str)
        self.peers_tree = Gtk.TreeView(model=self.peers_model)
        
        cols = [_("IP"), _("Host"), _("User"), _("System"), _("Ping")]
        for i, col_title in enumerate(cols):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(col_title, renderer, text=i)
            if i == 4: renderer.set_property("xalign", 0.5)
            column.set_resizable(True); column.set_expand(True if i == 1 else False)
            self.peers_tree.append_column(column)
        
        scroll_tree = Gtk.ScrolledWindow(vexpand=True); scroll_tree.set_child(self.peers_tree)
        scroll_tree.add_css_class("card")
        net_box.append(scroll_tree)
        
        self.connect_stack.add_titled(net_box, "network", _("Status"))
        
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        switcher = Adw.ViewSwitcher(stack=self.connect_stack)
        header.set_title_widget(switcher)
        self.connect_toolbar_view.add_top_bar(header)
        self.connect_toolbar_view.set_content(self.connect_stack)
        
        self.connect_stack.connect("notify::visible-child-name", self.on_connect_stack_changed)
        
        if self.mode == 'connect': GLib.timeout_add_seconds(10, self.refresh_peers)

        return self.connect_toolbar_view

    def on_connect_stack_changed(self, stack, param):
        if stack.get_visible_child_name() == "network":
            self.refresh_peers()

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

    def refresh_peers(self):
        if self.mode != 'connect': return False
        threading.Thread(target=self._get_tailscale_status, daemon=True).start()
        return True

    def _get_tailscale_status(self):
        try:
            if shutil.which("tailscale") is None: return
            import json, re
            result = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                peers_raw = []
                self_node = data.get('Self', {})
                peers_raw.append({'ip': self_node.get('TailscaleIPs', ['-'])[0], 'host': self_node.get('Hostname', _('Local')), 'user': self_node.get('User', '-'), 'os': self_node.get('OS', '-'), 'is_self': True})
                peer_nodes = data.get('Peer')
                if peer_nodes:
                    for p_id in peer_nodes:
                        node = peer_nodes[p_id]
                        peers_raw.append({'ip': node.get('TailscaleIPs', ['-'])[0], 'host': node.get('Hostname', '-'), 'user': node.get('User', '-'), 'os': node.get('OS', '-'), 'is_self': False})
                final_peers = []
                for p in peers_raw:
                    ping_val = "-"
                    if not p['is_self'] and p['ip'] != "-":
                        try:
                            ping_proc = subprocess.run(["ping", "-c", "1", "-W", "1", p['ip']], capture_output=True, text=True)
                            if ping_proc.returncode == 0:
                                match = re.search(r'time=([\d.]+) ms', ping_proc.stdout)
                                if match: ping_val = f"{match.group(1)} ms"
                        except: ping_val = "Error"
                    elif p['is_self']: ping_val = "0 ms"
                    final_peers.append((p['ip'], p['host'], p['user'], p['os'], ping_val))
                GLib.idle_add(self._update_peers_ui, final_peers)
        except: pass

    def _update_peers_ui(self, peers):
        self.peers_model.clear()
        for p in peers: self.peers_model.append(p)

    def on_next_clicked(self, button):
        n_pages = self.create_carousel.get_n_pages()
        current_idx = int(self.create_carousel.get_position())
        
        if current_idx == 0:
            if not self.entry_domain.get_text():
                self.main_window.show_toast(_("Domain is required"))
                return
        elif current_idx == 2:
            if not self.entry_zone.get_text() or not self.entry_token.get_text():
                self.main_window.show_toast(_("API Keys are required"))
                return
        
        if current_idx < n_pages - 1:
            next_page = self.create_carousel.get_nth_page(current_idx + 1)
            self.create_carousel.scroll_to(next_page, True)
            self.btn_back.set_sensitive(True)
            if current_idx + 1 == n_pages - 1: self.btn_next.set_label(_("Install Server"))
        else: self.run_install()

    def on_back_clicked(self, button):
        current_idx = int(self.create_carousel.get_position())
        if current_idx > 0:
            prev_page = self.create_carousel.get_nth_page(current_idx - 1)
            self.create_carousel.scroll_to(prev_page, True)
            self.btn_next.set_label(_("Next"))
            if current_idx - 1 == 0: self.btn_back.set_sensitive(False)

    def log(self, text, view=None):
        if view is None: view = self.text_view
        GLib.idle_add(self._log_idle, text, view)

    def _log_idle(self, text, view):
        buf = view.get_buffer(); buf.insert(buf.get_end_iter(), text + "\n")
        mark = buf.get_insert(); view.scroll_to_mark(mark, 0.0, True, 0.5, 1.0)

    def run_install(self):
        self.btn_next.set_sensitive(False)
        self.exec_label.set_text(_("Installing..."))
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
            while True:
                line = process.stdout.readline()
                if not line: break
                self.log(line.strip())
            process.wait()
            GLib.idle_add(self.on_install_finished, process.returncode)
        threading.Thread(target=thread_func, daemon=True).start()

    def on_install_finished(self, code):
        self.exec_label.set_text(_("Finished with code: {}").format(code))
        if code == 0: self.main_window.show_toast(_("Success!"))
        else: self.main_window.show_toast(_("Installation failed"))
        self.btn_next.set_sensitive(True); self.btn_next.set_label(_("Try Again"))

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
