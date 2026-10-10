"""Turn the single-file Vite build into an artifact fragment (no doctype/html/head/body)."""
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
head = re.search(r"<head>(.*)</head>", src, re.S).group(1)
body = re.search(r"<body>(.*)</body>", src, re.S).group(1)
title = re.search(r"<title>.*?</title>", head, re.S).group(0)
links = "\n".join(re.findall(r'<link[^>]+fonts\.g[^>]+>', head))
styles = "\n".join(re.findall(r"<style[^>]*>.*?</style>", head, re.S))
scripts = "\n".join(re.findall(r"<script[^>]*>.*?</script>", head, re.S))
out = f"{title}\n{links}\n{styles}\n{body.strip()}\n{scripts}\n"
open(sys.argv[2], "w", encoding="utf-8").write(out)
print(len(out), title)
