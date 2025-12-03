import paramiko, time

host = "172.16.70.39"
port = 5022
user = "dadmin"
password = "Avaya@123"

transport = paramiko.Transport((host, port))
transport.connect()
transport.auth_interactive(user, lambda t,i,p: [password if 'Password' in pr[0] else '' for pr in p])

channel = transport.open_session()
channel.get_pty(term='vt220')
channel.invoke_shell()
time.sleep(2)

if channel.recv_ready():
    banner = channel.recv(8192).decode(errors="ignore")
    print("=== RAW BANNER START ===")
    print(banner)
    print("=== RAW BANNER END ===")
transport.close()
