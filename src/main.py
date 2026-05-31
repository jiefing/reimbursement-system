import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import sqlite3
import os
import zipfile
import csv
import subprocess

# ================= 0. 数据库辅助功能 =================
def init_database():
    conn = sqlite3.connect('lab_billing_system.db')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS Reimbursement_Forms (
        order_id TEXT PRIMARY KEY, form_type TEXT, biz_id TEXT, book_time TEXT,
        fund_code TEXT, total_amount REAL, note TEXT, attachment_dir TEXT, reimburse_types TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS Invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_num TEXT, amount REAL,
        form_order_id TEXT, personnel_id INTEGER)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS Personnel (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, grade TEXT NOT NULL,
        student_id TEXT, title TEXT, phone TEXT, bank_card TEXT, note TEXT)''')

    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN note TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN attachment_dir TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE Invoices ADD COLUMN amount REAL")
    except: pass
    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN reimburse_types TEXT")
    except: pass
    
    conn.commit()

    # ！！！隐私保护：替换为张三李四的虚拟脱敏数据 ！！！
    cursor.execute("SELECT count(*) FROM Personnel")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Personnel (name, title, grade) VALUES ('张三', '测试研究员', '2024级博士')")
        cursor.execute("INSERT INTO Personnel (name, title, grade) VALUES ('李四', '教授', '教师团队')")
        conn.commit()
    conn.close()

def get_all_personnel_list():
    try:
        conn = sqlite3.connect('lab_billing_system.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM Personnel")
        records = cursor.fetchall()
        conn.close()
        return [f"{row[0]}-{row[1]}" for row in records]
    except: return []

def get_personnel_by_grade(grade_name):
    try:
        conn = sqlite3.connect('lab_billing_system.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM Personnel WHERE grade = ?", (grade_name,))
        records = cursor.fetchall()
        conn.close()
        return [f"{row[0]}-{row[1]}" for row in records]
    except: return []

def get_all_grades():
    try:
        conn = sqlite3.connect('lab_billing_system.db')
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT grade FROM Personnel WHERE grade IS NOT NULL AND grade != ''")
        records = cursor.fetchall()
        conn.close()
        return [row[0] for row in records]
    except: return []

# ================= 1. 核心解析引擎 =================
def extract_info(text):
    yuyue_danhao = re.search(r"预约单号：(\d+)", text)
    yewu_hao = re.search(r"业务号：([A-Za-z0-9]+)", text)
    yuyue_shijian = re.search(r"预约时间：([\d-]+)", text)
    jine_match = re.search(r"￥([\d,\.]+)", text)

    clean_text = re.sub(r"对方账号\s*:\s*\d+", "", text)
    fapiao_list = re.findall(r"\b\d{20}\b", clean_text)
    fapiao_haos = ", ".join(list(set(fapiao_list))) if fapiao_list else "无发票"

    # -------- 修复：识别经费号（项目号）--------
    jingfei_hao = ""
    danju_leixing = "未知类型"

    if "日常报销单" in text:
        danju_leixing = "日常报销单"
        # 日常报销单：经费号在表格第一列，用\t分隔
        # 先尝试直接搜索 "4300-B220163" 模式（tab分隔表格）
        table_section = re.search(
            r"经费号\s+支出内容\s+票据张数\s+金额\s+备注\s*\n(.*?)预约报销总金额",
            text, re.DOTALL)
        if table_section:
            table_text = table_section.group(1)
            found = set()
            for line in table_text.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("合计"):
                    continue
                cols = line.split("\t")
                if cols and re.match(r"\d{4}-[A-Za-z0-9]+", cols[0].strip()):
                    found.add(cols[0].strip())
            if found:
                jingfei_hao = ", ".join(sorted(found))
        # 若表格方式未找到，尝试冒号格式
        if not jingfei_hao:
            jingfei_match = re.search(r"经费号\s*[:：]\s*(\S+)", text)
            if jingfei_match:
                jingfei_hao = jingfei_match.group(1).strip()

    elif "差旅费报销单" in text:
        danju_leixing = "差旅费报销单"
        # 差旅单：经费号一般在同一行 "经费号：4300-XXXX"
        jingfei_match = re.search(r"经费号\s*[:：]\s*(\S+)", text)
        if jingfei_match:
            jingfei_hao = jingfei_match.group(1).strip()

    # -------- 修复：识别发票金额（从发票明细表提取）--------
    invoices = []  # 元素为 (发票号, 总金额)
    invoice_table_match = re.search(
        r"发票明细\s*\n序号\s+发票号.*?本人承诺",
        text, re.DOTALL)
    if invoice_table_match:
        # 使用更宽松的截取方式：从"发票明细"到"本人承诺"
        section = text[text.find("发票明细"):]
        end_pos = section.find("本人承诺")
        if end_pos != -1:
            section = section[:end_pos]
        lines = section.splitlines()
        header_passed = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "序号" in line and "发票号" in line:
                header_passed = True
                continue
            if not header_passed:
                continue
            if line.startswith("合计"):
                continue
            # 按 tab 分列（保留空列，确保索引正确），兼容连续空格
            cols = line.split("\t")
            # 如果 tab 分列后列数不足，尝试按连续空格拆分
            if len(cols) < 8:
                cols = re.split(r"\s{2,}", line)
            if len(cols) >= 8:
                inv_num = cols[1].strip()
                total_amt = cols[7].strip()
                invoices.append((inv_num, total_amt))
            elif len(cols) >= 3:
                inv_num = cols[1].strip() if len(cols) > 1 else ""
                total_amt = cols[-1].strip()
                invoices.append((inv_num, total_amt))
            elif len(cols) >= 3:
                # 兼容格式：至少要有序号、发票号、总金额
                inv_num = cols[1].strip() if len(cols) > 1 else ""
                total_amt = cols[-1].strip()
                invoices.append((inv_num, total_amt))

    # 若明细表未找到发票，则回退到附言中的20位发票号
    if not invoices and fapiao_list:
        for fp in set(fapiao_list):
            invoices.append((fp, ""))

    # -------- 修复：自动填写备注 + 差旅单归属人 --------
    note = ""
    if danju_leixing == "差旅费报销单":
        # 差旅单：提取出差人姓名作为归属人
        # 格式1: "出差人姓名\t赵六\t职别"
        cr_match = re.search(r"出差人姓名\s+(\S+?)\s+职别", text)
        if not cr_match:
            # 格式2: "出差人姓名\t赵六\t"
            cr_match = re.search(r"出差人姓名\t(\S+?)\t", text)
        if cr_match:
            note = f"归属人：{cr_match.group(1)}"
        # 若文本中还有"备注："内容，追加
        note_match = re.search(r"备注[：:][ \t]*([^\n]*)", text)
        if note_match:
            extra = note_match.group(1).strip()
            note = f"{note}；{extra}" if note else extra
    else:
        # 日常报销单：提取备注
        note_match = re.search(r"备注[：:][ \t]*(.*?)(?=\n\s*\n|虚线|$)", text, re.DOTALL)
        if note_match:
            note = re.sub(r"\s+", " ", note_match.group(1).strip())
        else:
            # 简单兜底：取备注冒号后第一行
            note_match2 = re.search(r"备注[：:][ \t]*([^\n]*)", text)
            if note_match2:
                note = note_match2.group(1).strip()

    guessed_types = []
    if "差旅" in text or "出差" in text or "交通" in text: guessed_types.append("差旅报销")
    if "办公耗材" in text or "文具" in text or "打印纸" in text: guessed_types.append("办公耗材")
    if "实验耗材" in text or "试剂" in text or "科研实验材料" in text: guessed_types.append("实验耗材")
    if "邮寄" in text or "快递" in text: guessed_types.append("邮寄服务")
    if "打印" in text or "复印" in text or "办公费" in text: guessed_types.append("办公服务")
    if "测序" in text or "检测" in text or "实验服务" in text: guessed_types.append("实验服务")
    if "技术服务" in text or "分析费" in text: guessed_types.append("技术服务")
    if "设备维修" in text or "维护" in text: guessed_types.append("设备维护")
    if "版面费" in text or "出版费" in text: guessed_types.append("版面费用")

    return {
        "单据类型": danju_leixing, "预约单号": yuyue_danhao.group(1) if yuyue_danhao else "",
        "业务号": yewu_hao.group(1) if yewu_hao else "", "预约时间": yuyue_shijian.group(1) if yuyue_shijian else "",
        "经费号": jingfei_hao, "总金额": jine_match.group(1) if jine_match else "",
        "发票号": fapiao_haos, "发票列表": invoices, "备注": note, "智能推断项目": guessed_types
    }

# ================= 2. 图形界面构建 =================
def start_app():
    init_database()

    root = tk.Tk()
    root.title("实验室报账系统 v1.0")
    root.geometry("1180x800")
    root.minsize(1000, 720)  # 防止窗口过小导致模块不显示
    bg_color = "#F8F8E7" 
    main_font = ("Consolas", 11)
    root.configure(bg=bg_color)

    # ---------------- 窗口一：人员管理 ----------------
    def open_personnel_window():
        p_win = tk.Toplevel(root)
        p_win.title("实验室人员信息库")
        p_win.geometry("900x500")
        p_win.configure(bg=bg_color)
        p_win.transient(root) 
        
        form_frame = tk.Frame(p_win, bg=bg_color)
        form_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(form_frame, text="姓名*:", bg=bg_color, font=main_font).grid(row=0, column=0, pady=5)
        name_e = tk.Entry(form_frame, font=main_font, width=12); name_e.grid(row=0, column=1, padx=5)
        tk.Label(form_frame, text="年级*:", bg=bg_color, font=main_font).grid(row=0, column=2)
        grade_e = tk.Entry(form_frame, font=main_font, width=12); grade_e.grid(row=0, column=3, padx=5)
        tk.Label(form_frame, text="学号:", bg=bg_color, font=main_font).grid(row=0, column=4)
        sid_e = tk.Entry(form_frame, font=main_font, width=15); sid_e.grid(row=0, column=5, padx=5)
        
        tk.Label(form_frame, text="职务/学位:", bg=bg_color, font=main_font).grid(row=1, column=0, pady=5)
        title_e = tk.Entry(form_frame, font=main_font, width=12); title_e.grid(row=1, column=1, padx=5)
        tk.Label(form_frame, text="手机号:", bg=bg_color, font=main_font).grid(row=1, column=2)
        phone_e = tk.Entry(form_frame, font=main_font, width=12); phone_e.grid(row=1, column=3, padx=5)
        tk.Label(form_frame, text="银行卡号:", bg=bg_color, font=main_font).grid(row=1, column=4)
        bank_e = tk.Entry(form_frame, font=main_font, width=20); bank_e.grid(row=1, column=5, padx=5)
        
        tk.Label(form_frame, text="备注:", bg=bg_color, font=main_font).grid(row=2, column=0, pady=5)
        note_e = tk.Entry(form_frame, font=main_font, width=33); note_e.grid(row=2, column=1, columnspan=3, padx=5, sticky=tk.W)
        
        columns = ("ID", "姓名", "年级", "学号", "银行卡号", "职务", "手机", "备注")
        tree = ttk.Treeview(p_win, columns=columns, show="headings", height=12)
        for col, width in zip(columns, [30, 80, 80, 120, 150, 80, 100, 150]):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def load_personnel_data():
            for item in tree.get_children(): tree.delete(item)
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute("SELECT id, name, grade, student_id, bank_card, title, phone, note FROM Personnel")
            for row in c.fetchall(): tree.insert("", tk.END, values=row)
            conn.close()

        def on_tree_select(event):
            selected = tree.selection()
            if not selected: return
            vals = tree.item(selected[0])['values']
            def clean_val(val): return "" if str(val) == "None" else str(val)
            name_e.delete(0, tk.END); name_e.insert(0, clean_val(vals[1]))
            grade_e.delete(0, tk.END); grade_e.insert(0, clean_val(vals[2]))
            sid_e.delete(0, tk.END); sid_e.insert(0, clean_val(vals[3]))
            bank_e.delete(0, tk.END); bank_e.insert(0, clean_val(vals[4]))
            title_e.delete(0, tk.END); title_e.insert(0, clean_val(vals[5]))
            phone_e.delete(0, tk.END); phone_e.insert(0, clean_val(vals[6]))
            note_e.delete(0, tk.END); note_e.insert(0, clean_val(vals[7]))
            
        tree.bind("<<TreeviewSelect>>", on_tree_select)

        def clear_entries():
            for entry in [name_e, grade_e, sid_e, title_e, phone_e, bank_e, note_e]: entry.delete(0, tk.END)

        def add_person():
            name, grade = name_e.get().strip(), grade_e.get().strip()
            if not name or not grade:
                return messagebox.showerror("缺少信息", "【姓名】和【年级】是必填项！", parent=p_win)
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute('''INSERT INTO Personnel (name, grade, student_id, title, phone, bank_card, note) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                      (name, grade, sid_e.get(), title_e.get(), phone_e.get(), bank_e.get(), note_e.get()))
            conn.commit(); conn.close()
            clear_entries()
            load_personnel_data()

        def edit_person():
            selected = tree.selection()
            if not selected:
                return messagebox.showwarning("提示", "请先在下方列表中点击选中要修改的人员！", parent=p_win)
            
            person_id = tree.item(selected[0])['values'][0]
            name, grade = name_e.get().strip(), grade_e.get().strip()
            if not name or not grade:
                return messagebox.showerror("缺少信息", "【姓名】和【年级】是必填项！", parent=p_win)
            
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute('''UPDATE Personnel SET name=?, grade=?, student_id=?, title=?, phone=?, bank_card=?, note=? WHERE id=?''', 
                      (name, grade, sid_e.get(), title_e.get(), phone_e.get(), bank_e.get(), note_e.get(), person_id))
            conn.commit(); conn.close()
            clear_entries()
            load_personnel_data()
            messagebox.showinfo("成功", "人员信息修改成功！", parent=p_win)

        def delete_person():
            selected = tree.selection()
            if not selected: return messagebox.showwarning("提示", "请选中人员！", parent=p_win)
            person_id, person_name = tree.item(selected[0])['values'][0], tree.item(selected[0])['values'][1]
            if messagebox.askyesno("确认删除", f"确定彻底删除【{person_name}】？", parent=p_win):
                conn = sqlite3.connect('lab_billing_system.db')
                conn.cursor().execute("DELETE FROM Personnel WHERE id=?", (person_id,))
                conn.commit(); conn.close()
                clear_entries()
                load_personnel_data()

        btn_frame = tk.Frame(p_win, bg=bg_color)
        btn_frame.pack(fill=tk.X, padx=10)
        tk.Button(btn_frame, text="➕ 新增人员", bg="#d9f2d9", font=("微软雅黑", 10), command=add_person).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="✏️ 保存修改", bg="#ffe6cc", font=("微软雅黑", 10), command=edit_person).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🗑️ 删除选中", bg="#ffb3b3", font=("微软雅黑", 10), command=delete_person).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔄 清空输入框", font=("微软雅黑", 10), command=clear_entries).pack(side=tk.LEFT, padx=20)
        
        load_personnel_data()

    # ---------------- 窗口二：数据查询 ----------------
    def open_export_window():
        e_win = tk.Toplevel(root)
        e_win.title("数据查询")
        e_win.geometry("1250x650")
        e_win.configure(bg=bg_color)
        e_win.transient(root)
        
        # ！！！核心机制：用后台字典锁死真实数据，彻底告别 Tkinter 吞 0 的 Bug ！！！
        row_data_map = {}
        
        def clean_val(v): return "" if v is None or str(v) == "None" else str(v)

        top_frame = tk.Frame(e_win, bg=bg_color)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        
        search_frame = tk.Frame(top_frame, bg=bg_color)
        search_frame.pack(side=tk.LEFT)
        
        tk.Label(search_frame, text="筛选：", bg=bg_color, font=("微软雅黑", 10)).pack(side=tk.LEFT)
        search_field_cmb = ttk.Combobox(search_frame, values=["预约单号", "业务号", "发票号", "发票归属人", "经费号", "报销项目"], 
                                        state="readonly", width=10, font=("微软雅黑", 10))
        search_field_cmb.current(0)
        search_field_cmb.pack(side=tk.LEFT, padx=5)
        
        search_keyword_entry = tk.Entry(search_frame, font=("微软雅黑", 10), width=18)
        search_keyword_entry.pack(side=tk.LEFT, padx=5)
        
        def get_all_data(field="", keyword=""):
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            query = """
                SELECT 
                    r.order_id, r.biz_id, r.form_type, r.book_time, r.fund_code, r.total_amount, r.reimburse_types,
                    i.invoice_num, i.amount, p.name, p.student_id, p.bank_card, r.note, r.attachment_dir, i.id 
                FROM Reimbursement_Forms r
                LEFT JOIN Invoices i ON r.order_id = i.form_order_id
                LEFT JOIN Personnel p ON i.personnel_id = p.id
            """
            field_map = {
                "预约单号": "r.order_id", "业务号": "r.biz_id", "发票号": "i.invoice_num", 
                "发票归属人": "p.name", "经费号": "r.fund_code", "报销项目": "r.reimburse_types"
            }
            params = ()
            if keyword and field in field_map:
                query += f" WHERE {field_map[field]} LIKE ?"
                params = (f"%{keyword}%",)
            query += " ORDER BY r.book_time DESC, r.order_id DESC"
            c.execute(query, params)
            data = c.fetchall()
            conn.close()
            return data

        def load_data_to_tree():
            for item in tree.get_children(): tree.delete(item)
            row_data_map.clear()
            
            field = search_field_cmb.get()
            keyword = search_keyword_entry.get().strip()
            data = get_all_data(field, keyword)
            
            last_order_id = None
            current_tag = 'group_a'
            
            for row in data:
                current_order_id = row[0]
                if current_order_id != last_order_id:
                    current_tag = 'group_b' if current_tag == 'group_a' else 'group_a'
                    last_order_id = current_order_id
                    
                clean_row = [clean_val(item) for item in row[:14]]
                item_id = tree.insert("", tk.END, values=clean_row, tags=(current_tag,))
                
                # 将真实的、没被篡改的数据库元组保存到后台字典中
                row_data_map[item_id] = row

        tk.Button(search_frame, text="🔍 筛选数据", bg="#e6e6e6", font=("微软雅黑", 9), command=load_data_to_tree).pack(side=tk.LEFT, padx=5)
        tk.Button(search_frame, text="🔄 取消筛选", bg="#e6e6e6", font=("微软雅黑", 9), command=lambda: [search_keyword_entry.delete(0, tk.END), load_data_to_tree()]).pack(side=tk.LEFT)

        def open_attachment():
            selected = tree.selection()
            if not selected: return messagebox.showwarning("提示", "请先选中记录！", parent=e_win)
            
            db_row = row_data_map.get(selected[0])
            if not db_row: return
            
            attach_path = clean_val(db_row[13])
            if not attach_path or not os.path.exists(attach_path):
                return messagebox.showinfo("无附件", "该记录没有附件或附件已丢失。", parent=e_win)
            try: subprocess.run(['explorer', '/select,', os.path.abspath(attach_path)])
            except Exception as e: messagebox.showerror("错误", f"打开位置失败：{e}", parent=e_win)

        def edit_selected():
            selected = tree.selection()
            if not selected:
                return messagebox.showwarning("提示", "请选中要修改的数据！", parent=e_win)
            
            # 直接从后台字典获取数据，拒绝 Tkinter 篡改
            db_row = row_data_map.get(selected[0])
            if not db_row: return
            
            old_order_id = clean_val(db_row[0])
            invoice_id = clean_val(db_row[14])

            edit_win = tk.Toplevel(e_win)
            edit_win.title(f"编辑明细 - 单号 {old_order_id}")
            edit_win.geometry("500x650")
            edit_win.configure(bg=bg_color)
            edit_win.transient(e_win)

            form_frame = tk.Frame(edit_win, bg=bg_color)
            form_frame.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

            fields_to_edit = [
                ("预约单号", clean_val(db_row[0])), ("业务号", clean_val(db_row[1])), ("单据类型", clean_val(db_row[2])),
                ("预约时间", clean_val(db_row[3])), ("经费号", clean_val(db_row[4])), ("总金额", clean_val(db_row[5])),
                ("报销项目", clean_val(db_row[6])), ("全局备注", clean_val(db_row[12])),
                ("--- 发票明细修改 ---", "---"),
                ("发票号", clean_val(db_row[7])), ("单张金额", clean_val(db_row[8])), ("发票归属人", clean_val(db_row[9]))
            ]

            edit_entries = {}
            person_cmb_edit = None
            
            for row_idx, (label_text, val) in enumerate(fields_to_edit):
                if val == "---":
                    tk.Label(form_frame, text=label_text, bg=bg_color, font=("微软雅黑", 10, "bold"), fg="#888").grid(row=row_idx, column=0, columnspan=2, pady=(15, 5))
                else:
                    tk.Label(form_frame, text=label_text + ":", bg=bg_color, font=("微软雅黑", 10)).grid(row=row_idx, column=0, sticky=tk.E, pady=5)
                    if label_text == "发票归属人":
                        person_cmb_edit = ttk.Combobox(form_frame, font=("微软雅黑", 10), width=26, state="readonly")
                        all_p = get_all_personnel_list()
                        person_cmb_edit['values'] = all_p
                        person_cmb_edit.grid(row=row_idx, column=1, pady=5, padx=5, sticky=tk.W)
                        for p_str in all_p:
                            if p_str.endswith(f"-{val}"): person_cmb_edit.set(p_str); break
                    else:
                        e = tk.Entry(form_frame, font=("微软雅黑", 10), width=28)
                        e.insert(0, val)
                        e.grid(row=row_idx, column=1, pady=5, padx=5, sticky=tk.W)
                        edit_entries[label_text] = e

            def save_edit():
                new_order_id = edit_entries["预约单号"].get().strip()
                try:
                    conn = sqlite3.connect('lab_billing_system.db')
                    c = conn.cursor()
                    
                    if new_order_id != old_order_id:
                        c.execute("UPDATE Reimbursement_Forms SET order_id=? WHERE order_id=?", (new_order_id, old_order_id))
                        c.execute("UPDATE Invoices SET form_order_id=? WHERE form_order_id=?", (new_order_id, old_order_id))
                    
                    c.execute("""UPDATE Reimbursement_Forms 
                                 SET biz_id=?, form_type=?, book_time=?, fund_code=?, total_amount=?, reimburse_types=?, note=? 
                                 WHERE order_id=?""", 
                              (edit_entries["业务号"].get(), edit_entries["单据类型"].get(), edit_entries["预约时间"].get(), 
                               edit_entries["经费号"].get(), edit_entries["总金额"].get(), edit_entries["报销项目"].get(), 
                               edit_entries["全局备注"].get(), new_order_id))
                    
                    if invoice_id and invoice_id != "":
                        p_str = person_cmb_edit.get()
                        p_id = p_str.split("-")[0] if "-" in p_str else None
                        c.execute("UPDATE Invoices SET invoice_num=?, amount=?, personnel_id=? WHERE id=?", 
                                  (edit_entries["发票号"].get(), edit_entries["单张金额"].get(), p_id, invoice_id))
                    
                    conn.commit(); conn.close()
                    messagebox.showinfo("成功", "数据修改成功！", parent=edit_win)
                    edit_win.destroy()
                    load_data_to_tree() 
                except Exception as e:
                    messagebox.showerror("错误", f"修改失败：{e}", parent=edit_win)

            tk.Button(edit_win, text="💾 保存修改", bg="#d9f2d9", font=("微软雅黑", 10, "bold"), command=save_edit).pack(pady=10)

        def delete_selected():
            selected = tree.selection()
            if not selected: return messagebox.showwarning("提示", "请先选中要删除的数据！", parent=e_win)
            
            # 直接从后台字典调取单号，杜绝开头的 0 被吞掉
            db_row = row_data_map.get(selected[0])
            if not db_row: return
            
            order_id = clean_val(db_row[0])
            invoice_id = clean_val(db_row[14])
            
            ans = messagebox.askyesnocancel("删除确认", 
                                            f"单号：{order_id}\n\n选【是】连根拔起：删除整张报销单及其发票\n选【否】仅删明细：只删除这一行发票\n选【取消】放弃",
                                            parent=e_win)
            if ans is None: return 
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            if ans is True:
                c.execute("DELETE FROM Reimbursement_Forms WHERE order_id=?", (order_id,))
                c.execute("DELETE FROM Invoices WHERE form_order_id=?", (order_id,))
            else:
                if invoice_id and invoice_id != "": c.execute("DELETE FROM Invoices WHERE id=?", (invoice_id,))
            conn.commit(); conn.close()
            load_data_to_tree()

        def export_to_excel():
            data = get_all_data(search_field_cmb.get(), search_keyword_entry.get().strip())
            if not data: return messagebox.showwarning("提示", "没有数据可导出！", parent=e_win)
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("Excel CSV 文件", "*.csv")],
                title="保存数据报表", initialfile="实验室报销明细汇总.csv", parent=e_win
            )
            if file_path:
                try:
                    with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        writer.writerow(columns) 
                        for row in data:
                            clean_row = [str(item).replace('\n', ' ') if item is not None else "" for item in row[:14]]
                            writer.writerow(clean_row)
                    messagebox.showinfo("导出成功", f"🎉 数据已导出至：\n{file_path}", parent=e_win)
                except Exception as e:
                    messagebox.showerror("导出失败", f"遇到错误：\n{e}", parent=e_win)

        btn_frame = tk.Frame(top_frame, bg=bg_color)
        btn_frame.pack(side=tk.RIGHT)
        
        tk.Button(btn_frame, text="📁 打开附件", bg="#e0ebeb", font=("微软雅黑", 9, "bold"), command=open_attachment).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="✏️ 编辑选中", bg="#ffe6cc", font=("微软雅黑", 9, "bold"), command=edit_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🗑️ 删除数据", bg="#ffb3b3", font=("微软雅黑", 9, "bold"), command=delete_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📥 导出全部", bg="#b3d9ff", font=("微软雅黑", 9, "bold"), command=export_to_excel).pack(side=tk.LEFT, padx=5)
        
        columns = ("预约单号", "业务号", "单据类型", "预约时间", "经费号", "总金额", "报销项目", "发票号", "单张金额", "发票归属人", "学号", "银行卡号", "备注", "附件路径")
        tree = ttk.Treeview(e_win, columns=columns, show="headings", height=20)
        
        tree.tag_configure('group_a', background='#ffffff')  
        tree.tag_configure('group_b', background='#e6f2ff')  
        
        col_widths = [120, 130, 100, 90, 100, 80, 130, 150, 80, 80, 120, 160, 120, 80]
        for col, width in zip(columns, col_widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor=tk.CENTER)
            
        scrollbar_y = ttk.Scrollbar(e_win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar_y.set)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x = ttk.Scrollbar(e_win, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=scrollbar_x.set)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        load_data_to_tree()

    # ================= 主界面布局 =================
    top_nav = tk.Frame(root, bg="#e0e0d1", height=40)
    top_nav.pack(side=tk.TOP, fill=tk.X)
    top_nav.pack_propagate(False) 
    tk.Button(top_nav, text="⚙️ 打开人员库管理", font=("微软雅黑", 10, "bold"), bg="#d9e6f2", command=open_personnel_window).pack(side=tk.LEFT, padx=10, pady=5)
    tk.Button(top_nav, text="📊 数据查询", font=("微软雅黑", 10, "bold"), bg="#ffd699", command=open_export_window).pack(side=tk.LEFT, padx=10, pady=5)

    main_content = tk.Frame(root, bg=bg_color)
    main_content.pack(fill=tk.BOTH, expand=True)

    left_frame = tk.Frame(main_content, bg=bg_color)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    right_frame = tk.Frame(main_content, bg=bg_color)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

    tk.Label(left_frame, text="1. 请在此处粘贴报销单文本：", bg=bg_color, font=main_font).pack(side=tk.TOP, anchor=tk.W)
    
    btn_frame_left = tk.Frame(left_frame, bg=bg_color)
    btn_frame_left.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

    text_input = tk.Text(left_frame, width=42, height=24, font=main_font)
    text_input.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(5, 0))

    def paste_text():
        try:
            clip_text = root.clipboard_get()
            text_input.delete("1.0", tk.END)
            text_input.insert(tk.END, clip_text)
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板为空或不是文本内容！", parent=root)

    def clear_text():
        text_input.delete("1.0", tk.END)

    tk.Button(btn_frame_left, text="📋 粘贴", font=("微软雅黑", 10), command=paste_text).pack(side=tk.LEFT, padx=(0, 5))
    tk.Button(btn_frame_left, text="🗑️ 清空", font=("微软雅黑", 10), command=clear_text).pack(side=tk.LEFT, padx=5)

    tk.Label(right_frame, text="2. 提取结果确认与编辑：", bg=bg_color, font=main_font).pack(anchor=tk.W, pady=(0, 5))

    top_info_frame = tk.Frame(right_frame, bg=bg_color)
    top_info_frame.pack(fill=tk.X, pady=(0, 10))

    info_left_frame = tk.Frame(top_info_frame, bg=bg_color)
    info_left_frame.pack(side=tk.LEFT, fill=tk.Y)

    info_right_frame = tk.Frame(top_info_frame, bg=bg_color)
    info_right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0)) 

    basic_info_frame = tk.Frame(info_left_frame, bg=bg_color)
    basic_info_frame.pack(fill=tk.X)
    
    entries = {}
    fields = ["单据类型", "预约单号", "业务号", "预约时间", "经费号", "总金额"]
    for field in fields:
        row = tk.Frame(basic_info_frame, bg=bg_color)
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text=field + "：", width=10, anchor=tk.E, bg=bg_color, font=main_font).pack(side=tk.LEFT)
        entry = tk.Entry(row, font=main_font, width=28)
        entry.pack(side=tk.LEFT, padx=5)
        entries[field] = entry 

    types_frame = tk.Frame(info_left_frame, bg=bg_color)
    types_frame.pack(fill=tk.X, pady=(15, 0))
    tk.Label(types_frame, text="报销项目 (可多选)：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    
    cb_container = tk.Frame(types_frame, bg=bg_color)
    cb_container.pack(fill=tk.X)
    
    reimburse_options = ["差旅报销", "办公耗材", "实验耗材", "邮寄服务", 
                         "办公服务", "实验服务", "技术服务", "设备维护", "版面费用", "其他"]
    type_vars = {}
    
    for i, opt in enumerate(reimburse_options):
        var = tk.BooleanVar()
        type_vars[opt] = var
        cb = tk.Checkbutton(cb_container, text=opt, variable=var, bg=bg_color, font=("微软雅黑", 9))
        cb.grid(row=i//3, column=i%3, sticky=tk.W, padx=2, pady=2)

    custom_frame1 = tk.Frame(cb_container, bg=bg_color)
    custom_frame1.grid(row=3, column=1, sticky=tk.W, padx=2, pady=2)
    custom_var1 = tk.BooleanVar()
    tk.Checkbutton(custom_frame1, variable=custom_var1, bg=bg_color).pack(side=tk.LEFT)
    custom_entry1 = tk.Entry(custom_frame1, font=("微软雅黑", 9), width=8)
    custom_entry1.pack(side=tk.LEFT)
    
    custom_frame2 = tk.Frame(cb_container, bg=bg_color)
    custom_frame2.grid(row=3, column=2, sticky=tk.W, padx=2, pady=2)
    custom_var2 = tk.BooleanVar()
    tk.Checkbutton(custom_frame2, variable=custom_var2, bg=bg_color).pack(side=tk.LEFT)
    custom_entry2 = tk.Entry(custom_frame2, font=("微软雅黑", 9), width=8)
    custom_entry2.pack(side=tk.LEFT)

    tk.Label(info_right_frame, text="备注：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    note_text = tk.Text(info_right_frame, height=3, font=main_font, width=30)
    note_text.pack(fill=tk.X, pady=(0, 10))
    entries["备注"] = note_text 

    tk.Label(info_right_frame, text="报销附件：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    attach_box_frame = tk.Frame(info_right_frame, bg=bg_color)
    attach_box_frame.pack(fill=tk.BOTH, expand=True)

    attach_listbox = tk.Listbox(attach_box_frame, height=4, font=main_font)
    attach_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    selected_attachments = [] 
    def browse_files():
        filepaths = filedialog.askopenfilenames(title="选择附件(支持多选)", filetypes=[("All Files", "*.*")])
        for fp in filepaths:
            if fp not in selected_attachments:
                selected_attachments.append(fp)
                attach_listbox.insert(tk.END, os.path.basename(fp))

    def clear_files():
        selected_attachments.clear()
        attach_listbox.delete(0, tk.END)

    btn_attach_box = tk.Frame(attach_box_frame, bg=bg_color)
    btn_attach_box.pack(side=tk.LEFT, padx=5)
    tk.Button(btn_attach_box, text="📎 浏览文件", font=("微软雅黑", 9), command=browse_files).pack(fill=tk.X, pady=2)
    tk.Button(btn_attach_box, text="🗑️ 清空列表", font=("微软雅黑", 9), command=clear_files).pack(fill=tk.X)

    tk.Label(right_frame, text="发票清单：", bg=bg_color, font=main_font).pack(anchor=tk.W, pady=(10, 0))

    # -------- 批量设置按钮 --------
    fill_btn_frame = tk.Frame(right_frame, bg=bg_color)
    fill_btn_frame.pack(fill=tk.X, padx=5, pady=(0, 2))
    tk.Button(fill_btn_frame, text="⚙️ 批量设置所属人", bg="#fff3cd", font=("微软雅黑", 9, "bold"),
              command=lambda: batch_set_person()).pack(side=tk.LEFT)

    # -------- 发票列表滚动区域（Canvas + Scrollbar）--------
    invoice_canvas = tk.Canvas(right_frame, bg=bg_color, highlightthickness=0, height=220)
    invoice_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=invoice_canvas.yview)
    invoice_canvas.configure(yscrollcommand=invoice_scrollbar.set)

    invoice_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    invoice_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

    invoice_frame = tk.Frame(invoice_canvas, bg=bg_color, bd=1, relief="sunken")
    invoice_window_id = invoice_canvas.create_window((0, 0), window=invoice_frame, anchor="nw")

    def _on_invoice_configure(event):
        invoice_canvas.configure(scrollregion=invoice_canvas.bbox("all"))
        # 让 invoice_frame 宽度跟随 canvas 宽度
        canvas_width = event.width
        invoice_canvas.itemconfig(invoice_window_id, width=canvas_width)

    def _on_canvas_configure(event):
        invoice_canvas.itemconfig(invoice_window_id, width=event.width)

    invoice_frame.bind("<Configure>", _on_invoice_configure)
    invoice_canvas.bind("<Configure>", _on_canvas_configure)

    # 鼠标滚轮滚动（跨平台，直接绑定到 canvas）
    def _on_mousewheel(event):
        # Windows / Mac
        if hasattr(event, 'delta') and event.delta != 0:
            delta = int(-1 * (event.delta / 120))
        else:
            # Linux: Button-4 (up), Button-5 (down)
            if hasattr(event, 'num') and event.num in (4, 5):
                delta = -1 if event.num == 4 else 1
            else:
                delta = 0
        if delta != 0:
            invoice_canvas.yview_scroll(delta, "units")

    invoice_canvas.bind("<MouseWheel>", _on_mousewheel)   # Windows/Mac
    invoice_canvas.bind("<Button-4>", lambda e: invoice_canvas.yview_scroll(-1, "units"))  # Linux up
    invoice_canvas.bind("<Button-5>", lambda e: invoice_canvas.yview_scroll(1, "units"))   # Linux down

    # 当鼠标在 invoice_frame 内部控件上滚动时，也触发 canvas 滚动
    def _bind_mousewheel_to_children(widget):
        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", lambda e: invoice_canvas.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda e: invoice_canvas.yview_scroll(1, "units"))
        for child in widget.winfo_children():
            _bind_mousewheel_to_children(child)
    # 延迟绑定（等发票行添加后再绑）
    def _schedule_bind_children():
        invoice_canvas.after(200, lambda: _bind_mousewheel_to_children(invoice_frame))
    invoice_canvas.after(200, _schedule_bind_children)

    sum_frame = tk.Frame(right_frame, bg=bg_color)
    sum_frame.pack(fill=tk.X, pady=2)
    sum_label = tk.Label(sum_frame, text="发票合计金额：0.00 元", font=("微软雅黑", 12, "bold"), fg="#d9534f", bg=bg_color)
    sum_label.pack(side=tk.RIGHT, padx=10)

    active_invoice_widgets = []
    
    def batch_set_person():
        """弹窗批量设置发票所属人（使用 Listbox 多选，更可靠）"""
        if not active_invoice_widgets:
            messagebox.showinfo("提示", "没有可设置的发票行！", parent=root)
            return

        popup = tk.Toplevel(root)
        popup.title("批量设置所属人")
        popup.geometry("520x480")
        popup.configure(bg=bg_color)
        popup.transient(root)
        popup.grab_set()

        # 顶部提示
        top_f = tk.Frame(popup, bg=bg_color)
        top_f.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(top_f, text=f"共 {len(active_invoice_widgets)} 行，按住 Ctrl 键可多选：",
                  bg=bg_color, font=("微软雅黑", 9)).pack(side=tk.LEFT)

        # Listbox 多选区域
        list_frame = tk.Frame(popup, bg=bg_color)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        lb = tk.Listbox(list_frame, selectmode=tk.MULTIPLE,
                         yscrollcommand=scrollbar.set,
                         font=("Consolas", 9), height=15,
                         bg="#FFFFFF", selectbackground="#cce5ff")
        scrollbar.config(command=lb.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for i, w in enumerate(active_invoice_widgets):
            fp_text = w["fp_entry"].get().strip() or f"第{i+1}行"
            amt_text = w["amt_entry"].get().strip()
            label = f"  {i+1:02d}. {fp_text}" + (f"  (¥{amt_text})" if amt_text else "")
            lb.insert(tk.END, label)

        # 底部：选择年级 + 人员 + 应用按钮
        bottom_f = tk.Frame(popup, bg=bg_color)
        bottom_f.pack(fill=tk.X, padx=10, pady=(5, 10))

        tk.Label(bottom_f, text="年级：", bg=bg_color, font=("微软雅黑", 9)).pack(side=tk.LEFT)
        grade_cmb_p = ttk.Combobox(bottom_f, font=("微软雅黑", 9), state="readonly", width=10)
        grade_cmb_p.pack(side=tk.LEFT, padx=(0, 10))
        all_g = get_all_grades()
        grade_cmb_p['values'] = all_g
        if all_g:
            grade_cmb_p.current(0)

        tk.Label(bottom_f, text="人员：", bg=bg_color, font=("微软雅黑", 9)).pack(side=tk.LEFT)
        person_cmb_p = ttk.Combobox(bottom_f, font=("微软雅黑", 9), state="readonly", width=14)
        person_cmb_p.pack(side=tk.LEFT, padx=(0, 10))

        def _on_grade_select(event=None):
            people = get_personnel_by_grade(grade_cmb_p.get())
            person_cmb_p['values'] = people
            if people:
                person_cmb_p.current(0)
        grade_cmb_p.bind("<<ComboboxSelected>>", _on_grade_select)
        _on_grade_select()

        def _apply():
            selected_indices = list(lb.curselection())
            if not selected_indices:
                messagebox.showwarning("提示", "请先按住 Ctrl 键，点击选择要设置的发票行！", parent=popup)
                return
            tg = grade_cmb_p.get()
            tp = person_cmb_p.get()
            if not tg or not tp:
                messagebox.showwarning("提示", "请先选择年级和人员！", parent=popup)
                return
            success_count = 0
            for i in selected_indices:
                try:
                    w = active_invoice_widgets[i]
                    w["grade_cmb"].set(tg)
                    people = get_personnel_by_grade(tg)
                    w["person_cmb"]['values'] = people
                    matched = False
                    for p in people:
                        if p == tp or p.endswith(f"-{tp}") or tp.endswith(f"-{p}"):
                            w["person_cmb"].set(p)
                            matched = True
                            break
                    if not matched and people:
                        w["person_cmb"].current(0)
                    success_count += 1
                except Exception as e:
                    print(f"Batch set error at row {i}: {e}")
            update_total_sum()
            messagebox.showinfo("完成", f"已设置 {success_count}/{len(selected_indices)} 行发票的所属人！", parent=popup)
            popup.destroy()

        tk.Button(bottom_f, text="✅ 应用设置", bg="#b3d9ff", font=("微软雅黑", 9, "bold"),
                  command=_apply).pack(side=tk.RIGHT, padx=5)
        tk.Button(bottom_f, text="全选", bg="#e6e6e6", font=("微软雅黑", 8),
                  command=lambda: lb.select_set(0, tk.END)).pack(side=tk.RIGHT, padx=5)
        tk.Button(bottom_f, text="取消全选", bg="#e6e6e6", font=("微软雅黑", 8),
                  command=lambda: lb.select_clear(0, tk.END)).pack(side=tk.RIGHT, padx=5)

    def update_total_sum(*args):
        total = 0.0
        for w in active_invoice_widgets:
            val = w["amt_entry"].get().strip().replace(',', '')
            if val:
                try: total += float(val)
                except ValueError: pass
        sum_label.config(text=f"发票合计金额：{total:.2f} 元")

    def add_invoice_row(invoice_num="", invoice_amt=""):
        row = tk.Frame(invoice_frame, bg=bg_color)
        row.pack(fill=tk.X, pady=3, padx=5)
        
        fp_entry = tk.Entry(row, font=main_font, width=21)
        fp_entry.insert(0, invoice_num)
        fp_entry.pack(side=tk.LEFT)
        
        tk.Label(row, text=" 金额:", bg=bg_color, font=main_font).pack(side=tk.LEFT)
        amt_entry = tk.Entry(row, font=main_font, width=8)
        amt_entry.insert(0, invoice_amt)  # ---- 修复：自动填写金额 ----
        update_total_sum()  # 手动触发金额合计计算
        amt_entry.pack(side=tk.LEFT)
        amt_entry.bind("<KeyRelease>", update_total_sum)

        tk.Label(row, text=" 年级:", bg=bg_color, font=main_font).pack(side=tk.LEFT)
        grade_cmb = ttk.Combobox(row, font=("微软雅黑", 10), state="readonly", width=8)
        grade_cmb.pack(side=tk.LEFT, padx=2)
        grade_cmb.config(postcommand=lambda: grade_cmb.config(values=get_all_grades()))
        
        tk.Label(row, text=" 人员:", bg=bg_color, font=main_font).pack(side=tk.LEFT)
        person_cmb = ttk.Combobox(row, font=("微软雅黑", 10), state="readonly", width=8)
        person_cmb.pack(side=tk.LEFT, padx=2)
        
        def on_grade_select(event):
            people = get_personnel_by_grade(grade_cmb.get())
            person_cmb['values'] = people
            if people: person_cmb.current(0)
            else: person_cmb.set('')
                
        grade_cmb.bind("<<ComboboxSelected>>", on_grade_select)
        
        all_grades = get_all_grades()
        if all_grades:
            grade_cmb['values'] = all_grades
            grade_cmb.current(0)
            on_grade_select(None)
            
        row_widgets = {"row_frame": row, "fp_entry": fp_entry, "amt_entry": amt_entry, "grade_cmb": grade_cmb, "person_cmb": person_cmb}
        active_invoice_widgets.append(row_widgets)

        def delete_this_row():
            active_invoice_widgets.remove(row_widgets) 
            row.destroy()
            update_total_sum()

        tk.Button(row, text="✖ 删除", bg="#ffb3b3", font=("微软雅黑", 8), command=delete_this_row).pack(side=tk.LEFT, padx=5)

    def execute_save_data():
        order_id = entries["预约单号"].get().strip()
        if not order_id:
            messagebox.showerror("保存失败", "【预约单号】不能为空！")
            return
            
        zip_path = ""
        if selected_attachments:
            archive_folder = "attachments_archive"
            if not os.path.exists(archive_folder):
                os.makedirs(archive_folder)
            zip_path = f"{archive_folder}/{order_id}_附件.zip"
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in selected_attachments:
                        zipf.write(file_path, arcname=os.path.basename(file_path))
            except Exception as e:
                messagebox.showerror("附件压缩失败", f"打包附件时出错：{e}")
                return

        note_content = entries["备注"].get("1.0", tk.END).strip()
        
        selected_types = [opt for opt, var in type_vars.items() if var.get()]
        if custom_var1.get() and custom_entry1.get().strip():
            selected_types.append(custom_entry1.get().strip())
        if custom_var2.get() and custom_entry2.get().strip():
            selected_types.append(custom_entry2.get().strip())
        types_str = ", ".join(selected_types) 

        try:
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()

            c.execute('''
                REPLACE INTO Reimbursement_Forms 
                (order_id, form_type, biz_id, book_time, fund_code, total_amount, note, attachment_dir, reimburse_types)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id, entries["单据类型"].get(), entries["业务号"].get(),
                entries["预约时间"].get(), entries["经费号"].get(),
                entries["总金额"].get().replace(',', ''), note_content, zip_path, types_str
            ))

            c.execute("DELETE FROM Invoices WHERE form_order_id=?", (order_id,))

            for w in active_invoice_widgets:
                fp_num = w["fp_entry"].get().strip()
                amt = w["amt_entry"].get().strip()
                person_str = w["person_cmb"].get()

                person_id = None
                if person_str and "-" in person_str: person_id = person_str.split("-")[0]

                if fp_num or amt:
                    c.execute("INSERT INTO Invoices (invoice_num, amount, form_order_id, personnel_id) VALUES (?, ?, ?, ?)", 
                              (fp_num, amt, order_id, person_id))

            conn.commit()
            conn.close()
            
            success_msg = f"🎉 单号 {order_id} 的数据已入库！\n报销项目：{types_str if types_str else '未选择'}"
            if zip_path: success_msg += f"\n📁 附件已压缩归档至：\n{zip_path}"
            messagebox.showinfo("大功告成", success_msg)
            
        except Exception as e:
            messagebox.showerror("数据库错误", f"保存出错：\n{e}")

    bottom_btn_frame = tk.Frame(right_frame, bg=bg_color)
    bottom_btn_frame.pack(fill=tk.X, pady=10)

    tk.Button(bottom_btn_frame, text="+ 手动新增发票", bg="#d9f2d9", font=("微软雅黑", 9), command=lambda: add_invoice_row("")).pack(side=tk.LEFT)
    tk.Button(bottom_btn_frame, text="💾 保存并归档入库", bg="#b3d9ff", font=("微软雅黑", 10, "bold"), command=execute_save_data).pack(side=tk.RIGHT)

    def on_extract_btn_click():
        try:
            raw_text = text_input.get("1.0", tk.END)
            if not raw_text.strip(): return messagebox.showwarning("提示", "请先粘贴文本！")
            result = extract_info(raw_text)
            
            for field in fields:
                entries[field].delete(0, tk.END) 
                entries[field].insert(0, result.get(field, "")) 
                
            entries["备注"].delete("1.0", tk.END)
            entries["备注"].insert("1.0", result.get("备注", ""))

            for var in type_vars.values(): var.set(False)
            for guessed_opt in result.get("智能推断项目", []):
                if guessed_opt in type_vars: type_vars[guessed_opt].set(True)
                    
            custom_var1.set(False); custom_entry1.delete(0, tk.END)
            custom_var2.set(False); custom_entry2.delete(0, tk.END)

            clear_files()
            active_invoice_widgets.clear()
            for widget in invoice_frame.winfo_children(): widget.destroy()
            update_total_sum()

            if result.get("发票列表"):
                for inv_num, inv_amt in result["发票列表"]:
                    add_invoice_row(inv_num, inv_amt)
            elif result.get("发票号") and result.get("发票号") != "无发票":
                for fp in result["发票号"].split(", "): add_invoice_row(fp) 
            update_total_sum()  # 添加完所有发票行后重新计算合计
        except Exception as e:
            messagebox.showerror("解析错误", f"解析文本时出现错误：\n{e}\n\n请检查文本格式是否正确，或联系开发者。") 

    tk.Button(btn_frame_left, text="解析文本 >>", font=("Consolas", 11, "bold"), bg="#d0d0d0", command=on_extract_btn_click).pack(side=tk.RIGHT)
    
    root.mainloop()

if __name__ == '__main__':
    start_app()