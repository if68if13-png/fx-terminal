#!/bin/zsh
cd ~/Documents/FX分析
python3 fx_fundamental.py
git add fx_data.json
git commit -m "自動更新"
git push
