curl -XPOST -t "file" http://localhost:8080/api/v1/pdf/stamp -F files=https://s3-agb-doc.conny.de/AGB+Mietpreisbremse.pdf -F stamp_text={text: K3, color: 0,0,0, position_name: tr} --output d5.pdf
