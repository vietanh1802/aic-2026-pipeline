# -*- coding: utf-8 -*-
"""Nạp backend/.env trước mọi module con.

preprocess.py đọc AIC_* ở mức module, nên load_dotenv() phải chạy trước
`from app.preprocess import ...` trong main.py — app/__init__.py là chỗ duy nhất
bảo đảm thứ tự đó. Trước đây chỉ agent.py gọi load_dotenv(), mà agent.py không
còn được import (endpoint /text-search đã bị xoá), nên .env chưa từng được đọc.

override=False: biến đặt sẵn trong shell thắng .env.
"""
from dotenv import load_dotenv

load_dotenv(override=False)
