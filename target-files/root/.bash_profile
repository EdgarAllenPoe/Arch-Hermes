# Run the Wi-Fi/SSH verifier only on the first local tty1 root login.
if [[ "$(tty 2>/dev/null || true)" == "/dev/tty1" \
   && ! -f /var/lib/arch-ssh-bootstrap/ssh-verified \
   && -x /usr/local/sbin/arch-ssh-firstboot ]]; then
    /usr/local/sbin/arch-ssh-firstboot
fi
