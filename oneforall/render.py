from common import APPS, OPT, ETC, validate_site


def php_locations(app, root):
    socket = f'unix:/run/oneforall-{app}/php.sock'
    common = f'''include /etc/nginx/fastcgi_params;
        fastcgi_pass {socket};
        fastcgi_param HTTPS on;
        fastcgi_param HTTP_AUTHORIZATION $http_authorization;
        fastcgi_read_timeout 300s;'''
    if app == 'oddworks':
        return f'''
    root {root}; index index.php;
    location ~ ^/(?:config|includes|install|tests|scripts|docs|packaging)(?:/|$) {{ deny all; }}
    location ~ \\.(?:sqlite|db|sql|md|sh|json|env|yml)$ {{ deny all; }}
    location ~ \\.php$ {{ try_files $uri =404; {common}
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; }}
    location / {{ try_files $uri $uri/ =404; }}
'''
    return f'''
    root {root}/web; index index.php;
    auth_basic "CNCToleQuotation";
    auth_basic_user_file /etc/oneforall/cnc.htpasswd;
    # Bearer API keeps its own authentication; no Basic header collision.
    location = /api/v1/quote {{ auth_basic off; {common}
        fastcgi_param SCRIPT_FILENAME {root}/api/v1/quote.php; }}
    location = /api/v1/quote.php {{ auth_basic off; {common}
        fastcgi_param SCRIPT_FILENAME {root}/api/v1/quote.php; }}
    location /api/ {{ deny all; }}
    location ~ \\.php$ {{ try_files $uri =404;
        # Browser administration writes must originate on this exact origin.
        if ($cnc_bad_origin = 1) {{ return 403; }}
        {common} fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; }}
    location / {{ try_files $uri $uri/ =404; }}
'''


def nginx(config, installed):
    c = validate_site(config)
    header = '''user www-data;
worker_processes auto;
pid /run/oneforall-nginx.pid;
error_log /var/log/oneforall-nginx.log warn;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    server_tokens off;
    access_log off;
    client_body_temp_path /var/lib/oneforall/nginx/body;
    proxy_temp_path /var/lib/oneforall/nginx/proxy;
    fastcgi_temp_path /var/lib/oneforall/nginx/fastcgi;
    uwsgi_temp_path /var/lib/oneforall/nginx/uwsgi;
    scgi_temp_path /var/lib/oneforall/nginx/scgi;
    map "$request_method:$http_origin" $cnc_bad_origin {
        default 0;
        ~^(POST|PUT|PATCH|DELETE): 1;
        ~^(POST|PUT|PATCH|DELETE):https://cnctolequotation.DOMAIN(:LANPORT)?$ 0;
    }
'''.replace('DOMAIN', c['domain'].replace('.', '\\.')).replace('LANPORT', str(c['lan_port']))
    if c.get('routing_mode') == 'paths':
        header = header.replace('    map ', '    map ', 1).replace('        default 0;',
            '        default 0;\n        ~^(POST|PUT|PATCH|DELETE):https://www.' + c['domain'].replace('.', '\\.') + '(:' + str(c['lan_port']) + ')?$ 0;', 1)
    blocks = []
    for public in (False, True):
        listen = f"127.0.0.1:{c['tunnel_port']}" if public else f"{c['lan_ip']}:{c['lan_port']} ssl"
        tls = '' if public else f"ssl_certificate {c['certificate']}; ssl_certificate_key {c['private_key']}; ssl_protocols TLSv1.2 TLSv1.3;"
        acl = '' if public else ' '.join(f'allow {n};' for n in c['lan_networks']) + ' deny all;'
        blocks.append(f'server {{ listen {listen} default_server; {tls} server_name _; return 444; }}')
        for app in ('portal', *APPS):
            host = ('www' if app == 'portal' else app) + '.' + c['domain']
            enabled = (app == 'portal' or app in installed) and (not public or (c['public_enabled'] and (app == 'portal' or app in c['public_apps'])))
            body = 'return 403;' if not enabled else ''
            if enabled and app == 'portal':
                body = f'''root /opt/oneforall/portal; index index.html;
                location / {{ try_files $uri $uri/ =404; }}
                location = /status.json {{ alias /var/lib/oneforall/public/status-{'public' if public else 'lan'}.json; add_header Cache-Control "no-store"; }}'''
                if c.get('routing_mode') == 'paths':
                    for target in APPS:
                        allowed = target in installed and (not public or (c['public_enabled'] and target in c['public_apps']))
                        body += path_locations(target, OPT / 'apps' / target / 'current', public, allowed)
            elif enabled and APPS[app]['kind'] == 'php':
                body = php_locations(app, OPT / 'apps' / app / 'current')
            elif enabled:
                upstream = 'http://unix:/run/oneforall-cableplan/app.sock' if app == 'cableplan' else f"http://127.0.0.1:{APPS[app]['port']}"
                channel = 'tunnel' if public else 'lan'
                body = f'''location / {{ proxy_pass {upstream};
                    proxy_set_header Host $http_host;
                    proxy_set_header X-Forwarded-Proto https;
                    proxy_set_header X-Forwarded-For $remote_addr;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header Forwarded "";
                    proxy_set_header X-CablePlan-Access-Channel {channel};
                    proxy_read_timeout 300s; }}'''
            if app != 'portal' and enabled and c.get('routing_mode') == 'paths':
                # Existing subdomain frontends also serve prefixed links during migration.
                body = path_locations(app, OPT / 'apps' / app / 'current', public, True) + body
            if app == 'portal' and not public:
                host += ' ' + c['lan_ip']
            limit = '8m' if app == 'cableplan' else '0'
            blocks.append(f'''server {{ listen {listen}; {tls}
                server_name {host}; {acl}
                client_max_body_size {limit};
                add_header X-Content-Type-Options nosniff always;
                add_header Referrer-Policy same-origin always;
                location ~ /\\. {{ deny all; }}
                {body}
            }}''')
    # nginx map regexes use first matching regex: exact allowed origin before rejection.
    text = header + '\n'.join(blocks) + '\n}\n'
    reject = '        ~^(POST|PUT|PATCH|DELETE): 1;\n'
    text = text.replace(reject, '').replace('    }\n', reject + '    }\n', 1)
    return text


def path_locations(app, root, public, enabled):
    prefix = '/' + app
    if not enabled:
        return f'location = {prefix} {{ return 403; }} location {prefix}/ {{ return 403; }}'
    if APPS[app]['kind'] == 'python':
        upstream = 'http://unix:/run/oneforall-cableplan/app.sock:/' if app == 'cableplan' else f"http://127.0.0.1:{APPS[app]['port']}/"
        channel = 'tunnel' if public else 'lan'
        return f'''location = {prefix} {{ return 308 {prefix}/; }}
        location {prefix}/ {{
            client_max_body_size {'8m' if app == 'cableplan' else '0'};
            proxy_pass {upstream};
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Forwarded "";
            proxy_set_header X-CablePlan-Access-Channel {channel};
            proxy_redirect off;
            proxy_read_timeout 300s;
        }}'''
    webroot = str(root) + ('/web' if app == 'cnctolequotation' else '')
    auth = '' if app == 'oddworks' else 'auth_basic "CNCToleQuotation"; auth_basic_user_file /etc/oneforall/cnc.htpasswd;'
    api = '' if app == 'oddworks' else f'''location ~ ^{prefix}/api/v1/quote(?:\\.php)?$ {{
        include /etc/nginx/fastcgi_params;
        fastcgi_pass unix:/run/oneforall-{app}/php.sock;
        fastcgi_param SCRIPT_FILENAME {root}/api/v1/quote.php;
        fastcgi_param HTTPS on;
        fastcgi_param HTTP_AUTHORIZATION $http_authorization;
    }}
    location {prefix}/api/ {{ deny all; }}'''
    return f'''location = {prefix} {{ return 308 {prefix}/; }}
    location = {prefix}/ {{ rewrite ^ {prefix}/index.php last; }}
    {api}
    location ~ ^{prefix}/(?:config|includes|install|tests|scripts|docs|packaging)(?:/|$) {{ deny all; }}
    location ~ ^{prefix}/.*\\.(?:sqlite|db|sql|md|sh|json|env|yml)$ {{ deny all; }}
    location ~ ^{prefix}/(?<script_{app}>.+\\.php)$ {{
        {auth}
        {'if ($cnc_bad_origin = 1) { return 403; }' if app == 'cnctolequotation' else ''}
        root {webroot};
        try_files /$script_{app} =404;
        include /etc/nginx/fastcgi_params;
        fastcgi_pass unix:/run/oneforall-{app}/php.sock;
        fastcgi_param SCRIPT_FILENAME {webroot}/$script_{app};
        fastcgi_param HTTPS on;
        fastcgi_param HTTP_AUTHORIZATION $http_authorization;
        fastcgi_read_timeout 300s;
    }}
    location {prefix}/ {{ {auth} alias {webroot}/; }}'''
