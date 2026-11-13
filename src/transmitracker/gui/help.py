"""Small local tooltips; opening external documentation is an explicit user action."""

import webbrowser

import customtkinter as ctk


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self.timer = widget, text, None, None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, _event=None):
        self.hide()
        self.timer = self.widget.after(500, self.show)

    def show(self):
        self.timer = None
        self.tip = ctk.CTkToplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.geometry(f"+{self.widget.winfo_rootx() + 10}+{self.widget.winfo_rooty() + 35}")
        ctk.CTkLabel(self.tip, text=self.text, wraplength=360, justify="left").pack(padx=10, pady=8)

    def hide(self, _event=None):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


def help_link(parent, text, url):
    label = ctk.CTkLabel(
        parent, text=text, text_color=("#006d86", "#68dded"), cursor="hand2", anchor="w"
    )
    label.pack(fill="x", padx=18, pady=5)
    label.bind("<Button-1>", lambda _event: webbrowser.open(url))
    Tooltip(label, "Abre documentación externa en su navegador solo al hacer clic.")
    return label
