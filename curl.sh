#!/usr/bin/env sh


#url='https://heic.digital/download-sample/chef-with-trumpet.heic'
HOST=http://localhost:8080
dir=$1
# HOST=https://pdf.conny.dev
cmd="-XPOST -t file '$HOST/api/v1/pdf/merge?name=72.pdf&dpi=72' --output $1.pdf --connect-timeout 600 --max-time 600"
echo -n $cmd
for file in `ls -1 $dir`; do
  echo -n " -F 'files=@$dir/$file'"
done
