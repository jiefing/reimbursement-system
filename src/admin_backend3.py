import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import shutil
from datetime import datetime
import csv
import re

# ================= 1. 安全机制：自动备份 =================
def auto_backup_db():
    db_file = 'lab_billing_system.db'
    if not os.path.exists(db_file): return  
    backup_dir = 'backups'
    if not os.path.exists(backup_dir): os.makedirs(backup_dir)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.db')
    try: shutil.copy2(db_file, backup_file)
    except Exception as e: print(f"备份失败: {e}")

# 安全的浮点数转换，防止空字符串或非法字符导致崩溃
def safe_float(val):
    try:
        if not val: return 0.0
        return float(str(val).replace(',', '').strip())
    except:
        return 0.0

# ================= 2. 后台主程序 =================
def start_admin_app():
    auto_backup_db()
    
    root = tk.Tk()
    root.title("数据管理系统 v1.0")
    root.geometry("1300x850")
    bg_color = "#f0f4f7"
    root.configure(bg=bg_color)
    
    style = ttk.Style()
    style.configure("Treeview", rowheight=25, font=("微软雅黑", 9))
    style.configure("Treeview.Heading", font=("微软雅黑", 10, "bold"))
    
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # =========================================================
    # ---------- 模块一：报销数据 ----------
    # =========================================================
    tab_bills = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_bills, text="📊 报销数据")
    
    toolbar_bills = tk.Frame(tab_bills, bg=bg_color)
    toolbar_bills.pack(fill=tk.X, pady=5)
    tk.Label(toolbar_bills, text="提示：双击表格修改数据，按回车保存（带有 🔒 的列为核心保护数据，禁止修改）。", fg="#555", bg=bg_color).pack(side=tk.LEFT)
    
    frame_tree_bills = tk.Frame(tab_bills)
    frame_tree_bills.pack(fill=tk.BOTH, expand=True, pady=5)
    
    scroll_y_bills = ttk.Scrollbar(frame_tree_bills, orient=tk.VERTICAL)
    scroll_x_bills = ttk.Scrollbar(frame_tree_bills, orient=tk.HORIZONTAL)
    
    cols_bills = ("🔒发票ID", "🔒预约单号", "业务号", "类型", "预约时间", "经费号", "单据总金额", "发票号", "单张金额", "项目", "全局备注", "🔒发票归属人")
    tree_bills = ttk.Treeview(frame_tree_bills, columns=cols_bills, show="headings", 
                              yscrollcommand=scroll_y_bills.set, xscrollcommand=scroll_x_bills.set)
    
    scroll_y_bills.config(command=tree_bills.yview); scroll_y_bills.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_x_bills.config(command=tree_bills.xview); scroll_x_bills.pack(side=tk.BOTTOM, fill=tk.X)
    tree_bills.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    tree_bills.tag_configure('oddrow', background='#ffffff')  
    tree_bills.tag_configure('evenrow', background='#f4f8fb') 
    
    widths_bills = [80, 110, 130, 100, 100, 120, 100, 180, 100, 150, 200, 100]
    for col, width in zip(cols_bills, widths_bills):
        tree_bills.heading(col, text=col)
        tree_bills.column(col, width=width, minwidth=width, stretch=True, anchor=tk.CENTER)

    # 日期解析器：把带中文的日期转换成可排序的数字元组
    def get_date_tuple(date_str):
        ds = str(date_str or "").strip()
        m = re.search(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})', ds) # 匹配 2026年1月14日 或 2026-01-14
        if m: return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (0, 0, 0)

    def load_bills_data():
        for item in tree_bills.get_children(): tree_bills.delete(item)
        if not os.path.exists('lab_billing_system.db'): return
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()
        c.execute("""
            SELECT i.id, r.order_id, r.biz_id, r.form_type, r.book_time, r.fund_code, r.total_amount, 
                   i.invoice_num, i.amount, r.reimburse_types, r.note, p.name
            FROM Reimbursement_Forms r
            LEFT JOIN Invoices i ON r.order_id = i.form_order_id
            LEFT JOIN Personnel p ON i.personnel_id = p.id
        """)
        rows = c.fetchall()
        conn.close()
        
        # ！！！核心修复：在 Python 中强制按真实日期排序，解决中文日期错乱问题 ！！！
        rows.sort(key=lambda x: (get_date_tuple(x[4]), str(x[1] or "")), reverse=True)
        
        for count, row in enumerate(rows):
            clean_row = [str(item) if item is not None else "" for item in row]
            tree_bills.insert("", tk.END, values=clean_row, tags=('evenrow' if count % 2 == 0 else 'oddrow',))

    def on_bills_double_click(event):
        region = tree_bills.identify("region", event.x, event.y)
        if region != "cell": return
        item_id = tree_bills.identify_row(event.y)
        column_id = tree_bills.identify_column(event.x)
        col_index = int(column_id[1:]) - 1 
        if col_index in [0, 1, 11]: 
            messagebox.showinfo("安全拦截", "带有 🔒 图标的列属于核心关联数据，\n请在主程序或通过 CSV 重新导入进行覆盖修改。")
            return
        x, y, width, height = tree_bills.bbox(item_id, column_id)
        current_value = tree_bills.item(item_id, 'values')[col_index]
        entry = tk.Entry(tree_bills, font=("微软雅黑", 10), bg="#ffffcc")
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.focus() 
        def save_edit(event):
            new_val = entry.get()
            invoice_id = tree_bills.item(item_id, 'values')[0]
            order_id = tree_bills.item(item_id, 'values')[1]
            try:
                conn = sqlite3.connect('lab_billing_system.db')
                c = conn.cursor()
                if col_index in [7, 8]: 
                    field_name = "invoice_num" if col_index == 7 else "amount"
                    if invoice_id: c.execute(f"UPDATE Invoices SET {field_name}=? WHERE id=?", (new_val, invoice_id))
                else:
                    field_name = ["", "", "biz_id", "form_type", "book_time", "fund_code", "total_amount", "", "", "reimburse_types", "note"][col_index]
                    c.execute(f"UPDATE Reimbursement_Forms SET {field_name}=? WHERE order_id=?", (new_val, order_id))
                conn.commit(); conn.close()
                entry.destroy(); load_bills_data()
            except Exception as e:
                messagebox.showerror("更新失败", f"错误：{e}")
                entry.destroy()
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", lambda e: entry.destroy())

    tree_bills.bind("<Double-1>", on_bills_double_click)
    
    # ！！！新增：一键重新计算所有报销单总金额的功能 ！！！
    def recalculate_totals():
        if not messagebox.askyesno("确认操作", "系统将扫描数据库，根据【每张发票的金额】自动重新计算并填补所有报销单的【单据总金额】。\n建议在导入旧数据后执行此操作，是否继续？"): return
        try:
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute("SELECT order_id FROM Reimbursement_Forms")
            forms = c.fetchall()
            update_count = 0
            for (order_id,) in forms:
                c.execute("SELECT SUM(amount) FROM Invoices WHERE form_order_id=?", (order_id,))
                res = c.fetchone()
                total = safe_float(res[0]) if res else 0.0
                c.execute("UPDATE Reimbursement_Forms SET total_amount=? WHERE order_id=?", (total, order_id))
                update_count += 1
            conn.commit(); conn.close()
            messagebox.showinfo("大功告成", f"✅ 成功重新计算了 {update_count} 份报销单的总金额！\n\n请刷新数据网格或查看可视化看板。")
            load_bills_data()
        except Exception as e:
            messagebox.showerror("计算失败", f"系统遇到错误：\n{e}")

    btn_frame_bills = tk.Frame(tab_bills, bg=bg_color)
    btn_frame_bills.pack(pady=10)
    tk.Button(btn_frame_bills, text="🔄 刷新报销数据", font=("微软雅黑", 10), command=load_bills_data).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame_bills, text="🧮 重新计算所有总金额", bg="#ffe6cc", font=("微软雅黑", 10, "bold"), command=recalculate_totals).pack(side=tk.LEFT, padx=10)


    # =========================================================
    # ---------- 模块二：实验室人员信息 ----------
    # =========================================================
    tab_personnel = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_personnel, text="👥 实验室人员信息")
    
    toolbar_person = tk.Frame(tab_personnel, bg=bg_color)
    toolbar_person.pack(fill=tk.X, pady=5)
    tk.Label(toolbar_person, text="提示：双击任意单元格直接修改。点击“新增空白行”可快速录入新人。", fg="#555", bg=bg_color).pack(side=tk.LEFT)
    
    frame_tree_person = tk.Frame(tab_personnel)
    frame_tree_person.pack(fill=tk.BOTH, expand=True, pady=5)
    
    scroll_y_person = ttk.Scrollbar(frame_tree_person, orient=tk.VERTICAL)
    scroll_x_person = ttk.Scrollbar(frame_tree_person, orient=tk.HORIZONTAL)
    
    cols_person = ("🔒系统ID", "姓名", "年级", "学号", "职务", "手机号", "银行卡号", "人员备注")
    tree_person = ttk.Treeview(frame_tree_person, columns=cols_person, show="headings",
                               yscrollcommand=scroll_y_person.set, xscrollcommand=scroll_x_person.set)
    
    scroll_y_person.config(command=tree_person.yview); scroll_y_person.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_x_person.config(command=tree_person.xview); scroll_x_person.pack(side=tk.BOTTOM, fill=tk.X)
    tree_person.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    tree_person.tag_configure('oddrow', background='#ffffff')  
    tree_person.tag_configure('evenrow', background='#eef7ea') 
    
    widths_person = [80, 100, 120, 150, 100, 150, 200, 250]
    for col, width in zip(cols_person, widths_person):
        tree_person.heading(col, text=col)
        tree_person.column(col, width=width, minwidth=width, stretch=True, anchor=tk.CENTER)

    def load_personnel_data():
        for item in tree_person.get_children(): tree_person.delete(item)
        if not os.path.exists('lab_billing_system.db'): return
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()
        c.execute("SELECT id, name, grade, student_id, title, phone, bank_card, note FROM Personnel ORDER BY id DESC")
        for count, row in enumerate(c.fetchall()):
            clean_row = [str(item) if item is not None else "" for item in row]
            tree_person.insert("", tk.END, values=clean_row, tags=('evenrow' if count % 2 == 0 else 'oddrow',))
        conn.close()

    def on_person_double_click(event):
        region = tree_person.identify("region", event.x, event.y)
        if region != "cell": return
        item_id = tree_person.identify_row(event.y)
        column_id = tree_person.identify_column(event.x)
        col_index = int(column_id[1:]) - 1 
        if col_index == 0: 
            messagebox.showinfo("安全拦截", "系统ID为底层唯一标识，不可修改。")
            return
        x, y, width, height = tree_person.bbox(item_id, column_id)
        current_value = tree_person.item(item_id, 'values')[col_index]
        entry = tk.Entry(tree_person, font=("微软雅黑", 10), bg="#ccffcc")
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, current_value)
        entry.focus() 
        def save_edit(event):
            new_val = entry.get().strip()
            person_id = tree_person.item(item_id, 'values')[0]
            try:
                conn = sqlite3.connect('lab_billing_system.db')
                c = conn.cursor()
                field_name = ["", "name", "grade", "student_id", "title", "phone", "bank_card", "note"][col_index]
                c.execute(f"UPDATE Personnel SET {field_name}=? WHERE id=?", (new_val, person_id))
                conn.commit(); conn.close()
                entry.destroy(); load_personnel_data()
            except Exception as e:
                messagebox.showerror("更新失败", f"错误：{e}")
                entry.destroy()
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", lambda e: entry.destroy())

    tree_person.bind("<Double-1>", on_person_double_click)
    
    def add_blank_person():
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()
        c.execute("INSERT INTO Personnel (name, grade) VALUES ('新人员(请双击修改)', '待定')")
        conn.commit(); conn.close()
        load_personnel_data()
        
    def delete_selected_person():
        selected = tree_person.selection()
        if not selected: return messagebox.showwarning("提示", "请先选中要删除的人员！")
        p_id = tree_person.item(selected[0])['values'][0]
        p_name = tree_person.item(selected[0])['values'][1]
        if messagebox.askyesno("危险操作", f"确定要永久删除人员【{p_name}】吗？\n删除后可能导致其名下的发票失去关联！"):
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute("DELETE FROM Personnel WHERE id=?", (p_id,))
            conn.commit(); conn.close()
            load_personnel_data()

    btn_frame_person = tk.Frame(tab_personnel, bg=bg_color)
    btn_frame_person.pack(pady=10)
    tk.Button(btn_frame_person, text="➕ 新增空白行", font=("微软雅黑", 10, "bold"), bg="#d9f2d9", command=add_blank_person).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame_person, text="🗑️ 删除选中人员", font=("微软雅黑", 10), bg="#ffb3b3", command=delete_selected_person).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame_person, text="🔄 刷新列表", font=("微软雅黑", 10), command=load_personnel_data).pack(side=tk.LEFT, padx=10)

    # =========================================================
    # ---------- 模块三：数据导入导出 ----------
    # =========================================================
    tab_import = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_import, text="📥 数据导入导出")
    
    hub_frame = tk.Frame(tab_import, bg=bg_color)
    hub_frame.pack(fill=tk.X, padx=20, pady=10)
    
    frame_finance = tk.LabelFrame(hub_frame, text=" 💰 报销单据数据 (主表+发票) ", font=("微软雅黑", 11, "bold"), bg=bg_color, padx=15, pady=15)
    frame_finance.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
    
    frame_personnel = tk.LabelFrame(hub_frame, text=" 👥 实验室人员花名册 ", font=("微软雅黑", 11, "bold"), bg=bg_color, padx=15, pady=15)
    frame_personnel.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

    csv_headers_finance = ["预约单号", "单据类型", "业务号", "预约时间", "经费号", "总金额", "报销项目", "全局备注", "发票号", "单张金额", "发票归属人"]
    csv_headers_personnel = ["系统ID", "姓名", "年级", "学号", "职务", "手机号", "银行卡号", "人员备注"]
    
    log_text = tk.Text(tab_import, height=18, font=("Consolas", 10), bg="#1e1e1e", fg="#00ff00")
    
    def log_msg(msg):
        log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        log_text.see(tk.END)
        root.update()

    def down_tpl_finance():
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="405报销数据_导入模板.csv")
        if not file_path: return
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers_finance)
            writer.writerow(["2026001", "日常报销单", "B123", "2026-03-12", "2024-ABC", "100.5", "办公耗材", "加急", "12345678901234567890", "100.5", "张三"])
        log_msg(f"✅ 生成报销模板：{file_path}")

    def exp_finance():
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="405全库报销数据备份.csv")
        if not file_path: return
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()
        c.execute("""
            SELECT r.order_id, r.form_type, r.biz_id, r.book_time, r.fund_code, r.total_amount, r.reimburse_types, r.note,
                   i.invoice_num, i.amount, p.name
            FROM Reimbursement_Forms r
            LEFT JOIN Invoices i ON r.order_id = i.form_order_id
            LEFT JOIN Personnel p ON i.personnel_id = p.id
            ORDER BY r.book_time DESC, r.order_id DESC
        """)
        data = c.fetchall(); conn.close()
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers_finance)
            for row in data:
                writer.writerow([str(item).replace('\n', ' ') if item is not None else "" for item in row])
        log_msg(f"✅ 成功导出 {len(data)} 条报销数据。")

    def imp_finance():
        file_path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not file_path: return
        if not messagebox.askyesno("警告", "导入的报销数据将覆盖已有【同单号】数据，是否继续？"): return
        try:
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute("SELECT name, id FROM Personnel")
            p_dict = {row[0]: row[1] for row in c.fetchall()}
            processed, count = set(), 0
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    count += 1
                    o_id = row.get("预约单号", "").strip()
                    if not o_id: continue 
                    c.execute('''REPLACE INTO Reimbursement_Forms VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                              (o_id, row.get("单据类型", ""), row.get("业务号", ""), row.get("预约时间", ""), 
                               row.get("经费号", ""), row.get("总金额", ""), row.get("全局备注", ""), "", row.get("报销项目", "")))
                    if o_id not in processed:
                        c.execute("DELETE FROM Invoices WHERE form_order_id=?", (o_id,))
                        processed.add(o_id)
                    p_name = row.get("发票归属人", "").strip()
                    p_id = p_dict.get(p_name)
                    if p_name and not p_id:
                        c.execute("INSERT INTO Personnel (name, grade) VALUES (?, '虚拟年级')", (p_name,))
                        p_id = c.lastrowid; p_dict[p_name] = p_id
                    c.execute("INSERT INTO Invoices (invoice_num, amount, form_order_id, personnel_id) VALUES (?, ?, ?, ?)", 
                              (row.get("发票号", "").strip(), row.get("单张金额", "").strip(), o_id, p_id))
            conn.commit(); conn.close()
            log_msg(f"✅ 报销单导入完毕！更新 {len(processed)} 单。提醒：请去[报销数据]页点击【重新计算总金额】以刷新统计数据。")
            load_bills_data()
        except Exception as e: log_msg(f"❌ 报销单导入失败：{e}")

    tk.Button(frame_finance, text="下载模板", bg="#e6f2ff", font=("微软雅黑", 10), command=down_tpl_finance).pack(side=tk.LEFT, padx=5, expand=True)
    tk.Button(frame_finance, text="导出全库CSV", bg="#ffe6cc", font=("微软雅黑", 10), command=exp_finance).pack(side=tk.LEFT, padx=5, expand=True)
    tk.Button(frame_finance, text="🚀 导入并覆盖", bg="#d9f2d9", font=("微软雅黑", 10, "bold"), command=imp_finance).pack(side=tk.LEFT, padx=5, expand=True)

    def down_tpl_person():
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="405人员信息_导入模板.csv")
        if not file_path: return
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers_personnel)
            writer.writerow(["", "李四", "2024级博士", "2024001", "研究员", "13800000000", "622202...", "说明：系统ID留空为新增，填入原有ID为修改。"])
        log_msg(f"✅ 生成人员模板：{file_path}")

    def exp_person():
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="405人员花名册备份.csv")
        if not file_path: return
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()
        c.execute("SELECT id, name, grade, student_id, title, phone, bank_card, note FROM Personnel")
        data = c.fetchall(); conn.close()
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers_personnel)
            for row in data:
                writer.writerow([str(item).replace('\n', ' ') if item is not None else "" for item in row])
        log_msg(f"✅ 成功导出 {len(data)} 条人员信息。")

    def imp_person():
        file_path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not file_path: return
        if not messagebox.askyesno("警告", "带有【系统ID】的人员将被覆盖更新，无ID的将被作为新人员录入，是否继续？"): return
        try:
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            cnt_upd, cnt_ins = 0, 0
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    p_id = row.get("系统ID", "").strip()
                    name = row.get("姓名", "").strip()
                    if not name: continue
                    params = (name, row.get("年级", ""), row.get("学号", ""), row.get("职务", ""), row.get("手机号", ""), row.get("银行卡号", ""), row.get("人员备注", ""))
                    if p_id:
                        c.execute("UPDATE Personnel SET name=?, grade=?, student_id=?, title=?, phone=?, bank_card=?, note=? WHERE id=?", (*params, p_id))
                        cnt_upd += 1
                    else:
                        c.execute("INSERT INTO Personnel (name, grade, student_id, title, phone, bank_card, note) VALUES (?, ?, ?, ?, ?, ?, ?)", params)
                        cnt_ins += 1
            conn.commit(); conn.close()
            log_msg(f"✅ 人员导入完毕！更新 {cnt_upd} 人，新增 {cnt_ins} 人。"); load_personnel_data()
        except Exception as e: log_msg(f"❌ 人员导入失败：{e}")

    tk.Button(frame_personnel, text="下载模板", bg="#e6f2ff", font=("微软雅黑", 10), command=down_tpl_person).pack(side=tk.LEFT, padx=5, expand=True)
    tk.Button(frame_personnel, text="导出全库CSV", bg="#ffe6cc", font=("微软雅黑", 10), command=exp_person).pack(side=tk.LEFT, padx=5, expand=True)
    tk.Button(frame_personnel, text="🚀 导入并更新", bg="#d9f2d9", font=("微软雅黑", 10, "bold"), command=imp_person).pack(side=tk.LEFT, padx=5, expand=True)

    tk.Label(tab_import, text="▼ 系统执行实时日志 ▼", font=("微软雅黑", 10, "bold"), bg=bg_color).pack(anchor=tk.W, padx=20, pady=(10, 0))
    log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
    log_msg("系统双通道引擎就绪，等待操作...")


    # =========================================================
    # ---------- 模块四：数据可视化看板 ----------
    # =========================================================
    tab_visual = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_visual, text="📈 可视化看板")
    
    top_vis_frame = tk.Frame(tab_visual, bg=bg_color)
    top_vis_frame.pack(fill=tk.X, pady=10, padx=20)
    
    draw_canvas = tk.Canvas(tab_visual, bg="#ffffff", bd=1, relief=tk.SUNKEN)
    draw_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    color_palette = ["#fbb4ae", "#b3cde3", "#ccebc5", "#decbe4", "#fed9a6", "#ffffcc", "#e5d8bd", "#fddaec", "#f2f2f2"]

    def draw_native_charts():
        draw_canvas.delete("all")
        draw_canvas.update()
        c_width = draw_canvas.winfo_width()
        c_height = draw_canvas.winfo_height()
        if c_width < 100: c_width = 1000
        if c_height < 100: c_height = 600

        if not os.path.exists('lab_billing_system.db'): 
            draw_canvas.create_text(c_width/2, c_height/2, text="尚未建立数据库", font=("微软雅黑", 14), fill="#999")
            return
            
        conn = sqlite3.connect('lab_billing_system.db')
        c = conn.cursor()

        # 1. 饼图：报销分类占比（使用 safe_float 保障健壮性）
        c.execute("SELECT reimburse_types, total_amount FROM Reimbursement_Forms")
        cat_data = {}
        for row in c.fetchall():
            types_str = str(row[0] or "").strip()
            amt = safe_float(row[1])
            types = [t.strip() for t in types_str.split(',') if t.strip()]
            if not types: types = ["未分类"]
            split_amt = amt / len(types)
            for t in types: cat_data[t] = cat_data.get(t, 0) + split_amt
        cat_data_clean = {k: v for k, v in cat_data.items() if v > 0}

        # 2. 柱状图：人员Top10
        c.execute("""
            SELECT p.name, SUM(i.amount) FROM Invoices i
            LEFT JOIN Personnel p ON i.personnel_id = p.id
            WHERE p.name IS NOT NULL
            GROUP BY p.name ORDER BY SUM(i.amount) DESC LIMIT 10
        """)
        person_data = c.fetchall()

        # 3. 柱状图：各经费号使用情况（通过 Python 处理以防 SQL 计算字符出错）
        c.execute("SELECT fund_code, total_amount FROM Reimbursement_Forms WHERE fund_code IS NOT NULL AND fund_code != ''")
        fund_data_dict = {}
        for row in c.fetchall():
            fc = str(row[0]).strip()
            amt = safe_float(row[1])
            fund_data_dict[fc] = fund_data_dict.get(fc, 0.0) + amt
        # 只保留金额大于 0 的，并从大到小排序
        fund_data = sorted([(k, v) for k, v in fund_data_dict.items() if v > 0], key=lambda x: x[1], reverse=True)
        conn.close()

        # ================== 绘制左上：分类饼图 ==================
        draw_canvas.create_text(c_width*0.25, c_height*0.05, text="各项报销经费占比", font=("微软雅黑", 14, "bold"))
        if cat_data_clean:
            total_amt = sum(cat_data_clean.values())
            cx, cy = c_width * 0.25, c_height * 0.28
            r = min(c_width*0.15, c_height*0.18)
            box = (cx - r, cy - r, cx + r, cy + r)
            start_ang = 0
            legend_y = cy - r
            for i, (cat_name, amt) in enumerate(cat_data_clean.items()):
                extent_ang = (amt / total_amt) * 360
                color = color_palette[i % len(color_palette)]
                draw_canvas.create_arc(box, start=start_ang, extent=extent_ang, fill=color, outline="white", width=1.5)
                draw_canvas.create_rectangle(cx + r + 30, legend_y, cx + r + 45, legend_y + 15, fill=color, outline="")
                draw_canvas.create_text(cx + r + 55, legend_y + 7, text=f"{cat_name} ({(amt / total_amt) * 100:.1f}%)", anchor=tk.W, font=("微软雅黑", 9))
                start_ang += extent_ang; legend_y += 20
        else:
            draw_canvas.create_text(c_width*0.25, c_height*0.28, text="暂无分类数据", fill="#999")

        # ================== 绘制右上：人员 Top10 ==================
        draw_canvas.create_text(c_width*0.75, c_height*0.05, text="人员报销总额 Top 10", font=("微软雅黑", 14, "bold"))
        if person_data:
            chart_x_start, chart_y_bottom = c_width * 0.55, c_height * 0.45
            chart_w, chart_h = c_width * 0.4, c_height * 0.3
            draw_canvas.create_line(chart_x_start, chart_y_bottom, chart_x_start + chart_w, chart_y_bottom, width=2)
            draw_canvas.create_line(chart_x_start, chart_y_bottom, chart_x_start, chart_y_bottom - chart_h, width=2)
            
            names = [str(row[0]) for row in person_data]
            amts = [safe_float(row[1]) for row in person_data]
            max_amt = max(amts) if amts else 1
            bar_width, padding = (chart_w - 40) / len(names), ((chart_w - 40) / len(names)) * 0.2
            
            for i in range(1, 5):
                ly = chart_y_bottom - (chart_h * (i/4))
                draw_canvas.create_line(chart_x_start, ly, chart_x_start + chart_w, ly, fill="#e0e0e0", dash=(4, 4))
                draw_canvas.create_text(chart_x_start - 5, ly, text=f"{max_amt*(i/4):.0f}", anchor=tk.E, font=("微软雅黑", 8), fill="#666")

            for i, (name, amt) in enumerate(zip(names, amts)):
                x0, y0 = chart_x_start + 20 + i * bar_width + padding/2, chart_y_bottom
                x1, y1 = x0 + bar_width - padding, chart_y_bottom - ((amt / max_amt) * chart_h)
                draw_canvas.create_rectangle(x0, y0, x1, y1, fill="#5c9ebf", outline="#3b7a99")
                draw_canvas.create_text((x0+x1)/2, y1 - 10, text=f"{amt:.1f}", font=("微软雅黑", 8))
                draw_canvas.create_text((x0+x1)/2, y0 + 15, text=name, font=("微软雅黑", 9), anchor=tk.N)
        else:
            draw_canvas.create_text(c_width*0.75, c_height*0.28, text="暂无人员数据", fill="#999")

        # ================== 绘制下半区：经费号 ==================
        draw_canvas.create_text(c_width*0.5, c_height*0.55, text="各经费号累计使用金额", font=("微软雅黑", 14, "bold"))
        if fund_data:
            chart_x_start, chart_y_bottom = c_width * 0.1, c_height * 0.95
            chart_w, chart_h = c_width * 0.8, c_height * 0.3
            draw_canvas.create_line(chart_x_start, chart_y_bottom, chart_x_start + chart_w, chart_y_bottom, width=2)
            draw_canvas.create_line(chart_x_start, chart_y_bottom, chart_x_start, chart_y_bottom - chart_h, width=2)
            
            names = [row[0] for row in fund_data]
            amts = [row[1] for row in fund_data]
            max_amt = max(amts) if amts else 1
            bar_width, padding = (chart_w - 40) / len(names), ((chart_w - 40) / len(names)) * 0.2
            
            for i in range(1, 5):
                ly = chart_y_bottom - (chart_h * (i/4))
                draw_canvas.create_line(chart_x_start, ly, chart_x_start + chart_w, ly, fill="#e0e0e0", dash=(4, 4))
                draw_canvas.create_text(chart_x_start - 5, ly, text=f"{max_amt*(i/4):.0f}", anchor=tk.E, font=("微软雅黑", 8), fill="#666")

            for i, (name, amt) in enumerate(zip(names, amts)):
                x0, y0 = chart_x_start + 20 + i * bar_width + padding/2, chart_y_bottom
                x1, y1 = x0 + bar_width - padding, chart_y_bottom - ((amt / max_amt) * chart_h)
                draw_canvas.create_rectangle(x0, y0, x1, y1, fill="#8bc34a", outline="#689f38")
                draw_canvas.create_text((x0+x1)/2, y1 - 10, text=f"{amt:.1f}", font=("微软雅黑", 8))
                draw_canvas.create_text((x0+x1)/2, y0 + 15, text=name, font=("微软雅黑", 9), anchor=tk.N)
        else:
            draw_canvas.create_text(c_width*0.5, c_height*0.75, text="暂无经费数据", fill="#999")

    tk.Button(top_vis_frame, text="🔄 刷新并生成最新图表", font=("微软雅黑", 11, "bold"), bg="#d9e6f2", command=draw_native_charts).pack(side=tk.LEFT)
    draw_canvas.bind("<Configure>", lambda event: draw_native_charts())

    # =========================================================
    # ---------- 模块五：发票查验（防重防漏） ----------
    # =========================================================
    tab_invoice_check = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_invoice_check, text="🧾 发票查验")
    
    # 顶部查询区
    search_frame = tk.Frame(tab_invoice_check, bg="#ffffff", pady=15, padx=20)
    search_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
    
    tk.Label(search_frame, text="🔍 请输入发票号码:", font=("微软雅黑", 12, "bold"), bg="#ffffff").pack(side=tk.LEFT, padx=(0, 10))
    
    inv_entry = ttk.Entry(search_frame, font=("微软雅黑", 12), width=30)
    inv_entry.pack(side=tk.LEFT, padx=10)
    inv_entry.focus() # 自动聚焦

    # 结果展示区
    result_frame = tk.Frame(tab_invoice_check, bg=bg_color)
    result_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
    
    scrollbar_check = ttk.Scrollbar(result_frame)
    scrollbar_check.pack(side=tk.RIGHT, fill=tk.Y)
    
    result_text = tk.Text(result_frame, font=("微软雅黑", 11), bg="#ffffff", 
                          yscrollcommand=scrollbar_check.set, relief=tk.FLAT, padx=15, pady=15)
    result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar_check.config(command=result_text.yview)
    
    # 设置不同的文本样式标签
    result_text.tag_config("error", foreground="#d32f2f", font=("微软雅黑", 13, "bold"))
    result_text.tag_config("success", foreground="#2e7d32", font=("微软雅黑", 13, "bold"))
    result_text.tag_config("highlight", foreground="#1565c0", font=("微软雅黑", 11, "bold"))
    
    result_text.insert(tk.END, "系统就绪，请在上方输入发票号码并按回车键查询...\n")
    result_text.config(state=tk.DISABLED)

    # 核心查询逻辑
    def execute_invoice_query(event=None):
        inv_num = inv_entry.get().strip()
        if not inv_num:
            messagebox.showwarning("提示", "请输入发票号码！")
            return
        
        result_text.config(state=tk.NORMAL)
        result_text.delete("1.0", tk.END)
        
        if not os.path.exists('lab_billing_system.db'):
            result_text.insert(tk.END, "❌ 错误：数据库文件不存在。\n", "error")
            result_text.config(state=tk.DISABLED)
            return

        try:
            conn = sqlite3.connect('lab_billing_system.db')
            cursor = conn.cursor()
            
            # 第一步：联表查询发票表和人员表
            cursor.execute("""
                SELECT i.amount, i.form_order_id, p.name 
                FROM Invoices i
                LEFT JOIN Personnel p ON i.personnel_id = p.id
                WHERE i.invoice_num = ?
            """, (inv_num,))
            invoice_records = cursor.fetchall()
            
            if not invoice_records:
                result_text.insert(tk.END, f"\n 🟢 安全：发票号码【{inv_num}】尚未录入系统，可以正常报销。\n", "success")
            else:
                result_text.insert(tk.END, f"\n 🔴 警告命中：发票号码【{inv_num}】已在系统中存在 {len(invoice_records)} 条记录！\n", "error")
                result_text.insert(tk.END, "━" * 70 + "\n\n")
                
                # 第二步：循环查出具体的报销单详情
                for idx, (inv_amount, order_id, person_name) in enumerate(invoice_records):
                    cursor.execute("SELECT * FROM Reimbursement_Forms WHERE order_id = ?", (order_id,))
                    form_data = cursor.fetchone()
                    
                    person_display = person_name if person_name else '未知人员'
                    
                    if form_data:
                        # 字段对照: order_id, form_type, biz_id, book_time, fund_code, total_amount, note, attachment_dir, reimburse_types
                        f_order_id, f_form_type, f_biz_id, f_book_time, f_fund_code, f_total_amount, f_note, f_attachment, f_types = form_data
                        
                        result_text.insert(tk.END, f" 📄 【录入详情 {idx+1}】\n", "highlight")
                        result_text.insert(tk.END, f" ---------------------------------------------------------\n")
                        result_text.insert(tk.END, f" 👤 发票归属人: {person_display}\n")
                        result_text.insert(tk.END, f" 💴 该发票金额: ￥{safe_float(inv_amount):.2f}\n")
                        result_text.insert(tk.END, f" 🏷️ 关联预约单号: {f_order_id}\n")
                        result_text.insert(tk.END, f" 🎫 业务号: {f_biz_id if f_biz_id else '无'}\n")
                        result_text.insert(tk.END, f" 💳 经费代码: {f_fund_code if f_fund_code else '无'}\n")
                        result_text.insert(tk.END, f" 📅 报账时间: {f_book_time if f_book_time else '无'}\n")
                        result_text.insert(tk.END, f" 📑 单据类型: {f_form_type} - {f_types if f_types else '无分类'}\n")
                        result_text.insert(tk.END, f" 💰 主单总金额: ￥{safe_float(f_total_amount):.2f}\n")
                        result_text.insert(tk.END, f" 💡 备注信息: {f_note if f_note else '无'}\n\n")
                    else:
                        result_text.insert(tk.END, f" ⚠️ 数据异常：该发票关联的主单【{order_id}】在数据库中丢失。\n\n")
                        
        except Exception as e:
            result_text.insert(tk.END, f"\n ⛔ 查询出错：{str(e)}\n", "error")
        finally:
            if 'conn' in locals():
                conn.close()
            result_text.config(state=tk.DISABLED)

    # 绑定回车键和按钮
    inv_entry.bind('<Return>', execute_invoice_query)

    search_btn = tk.Button(search_frame, text="一键查验", bg="#4a90e2", fg="white", 
                           font=("微软雅黑", 11, "bold"), relief=tk.FLAT, padx=20, 
                           cursor="hand2", command=execute_invoice_query)
    search_btn.pack(side=tk.LEFT, padx=20)

# =========================================================
    # ---------- 模块六：数据备份与恢复 ----------
    # =========================================================
    tab_backup = tk.Frame(notebook, bg=bg_color)
    notebook.add(tab_backup, text="💾 备份与恢复")

    # 顶部工具栏
    backup_toolbar = tk.Frame(tab_backup, bg=bg_color)
    backup_toolbar.pack(fill=tk.X, padx=20, pady=15)

    tk.Label(backup_toolbar, text="💡 提示：系统每次启动会自动备份。您也可以在此手动备份。恢复前系统会自动创建一个紧急快照以防万一。", fg="#555", bg=bg_color, font=("微软雅黑", 10)).pack(side=tk.LEFT)

    # 列表区域
    frame_tree_backup = tk.Frame(tab_backup)
    frame_tree_backup.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

    scroll_y_backup = ttk.Scrollbar(frame_tree_backup, orient=tk.VERTICAL)
    tree_backup = ttk.Treeview(frame_tree_backup, columns=("文件名", "备份时间", "文件大小(KB)"), show="headings", yscrollcommand=scroll_y_backup.set)
    scroll_y_backup.config(command=tree_backup.yview)
    scroll_y_backup.pack(side=tk.RIGHT, fill=tk.Y)
    tree_backup.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    tree_backup.heading("文件名", text="备份文件名称")
    tree_backup.heading("备份时间", text="备份时间")
    tree_backup.heading("文件大小(KB)", text="文件大小 (KB)")

    tree_backup.column("文件名", width=350, anchor=tk.W)
    tree_backup.column("备份时间", width=250, anchor=tk.CENTER)
    tree_backup.column("文件大小(KB)", width=150, anchor=tk.E)

    tree_backup.tag_configure('oddrow', background='#ffffff')  
    tree_backup.tag_configure('evenrow', background='#f4f8fb') 

    # 核心逻辑：加载列表
    def load_backup_list():
        for item in tree_backup.get_children():
            tree_backup.delete(item)
        
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            return

        files = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        # 按文件的最后修改时间降序排序（最新的在最上面）
        files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)), reverse=True)

        for count, filename in enumerate(files):
            filepath = os.path.join(backup_dir, filename)
            # 解析真实的系统修改时间
            mtime = os.path.getmtime(filepath)
            time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            # 计算文件大小 (保留两位小数)
            size_kb = round(os.path.getsize(filepath) / 1024, 2)
            
            tree_backup.insert("", tk.END, values=(filename, time_str, f"{size_kb} KB"), tags=('evenrow' if count % 2 == 0 else 'oddrow',))

    # 核心逻辑：手动新建备份
    def manual_backup():
        db_file = 'lab_billing_system.db'
        if not os.path.exists(db_file):
            messagebox.showerror("错误", "当前没有找到数据库文件，无法备份！")
            return
        backup_dir = 'backups'
        if not os.path.exists(backup_dir): os.makedirs(backup_dir)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(backup_dir, f'db_backup_manual_{timestamp}.db')
        try:
            shutil.copy2(db_file, backup_file)
            messagebox.showinfo("成功", f"✅ 手动备份成功！\n\n文件已保存为：\n{backup_file}")
            load_backup_list()
        except Exception as e:
            messagebox.showerror("失败", f"备份失败: {e}")

    # 核心逻辑：恢复选中的备份
    def restore_backup():
        selected = tree_backup.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在列表中点击选中一个要恢复的备份文件！")
            return
        
        filename = tree_backup.item(selected[0])['values'][0]
        backup_dir = 'backups'
        backup_file = os.path.join(backup_dir, filename)
        db_file = 'lab_billing_system.db'

        # 危险操作确认
        confirm_msg = f"⚠️ 危险操作警告 ⚠️\n\n您确定要将整个系统数据恢复至：\n【{filename}】吗？\n\n恢复后，当前未备份的新数据将被覆盖！\n(系统会自动执行一次失败保护快照)"
        if not messagebox.askyesno("确认恢复", confirm_msg, icon='warning'):
            return

        try:
            # 安全机制：恢复前给当前正在使用的数据库拍个快照 (failsafe)
            if os.path.exists(db_file):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                failsafe_file = os.path.join(backup_dir, f'db_failsafe_before_restore_{timestamp}.db')
                shutil.copy2(db_file, failsafe_file)

            # 正式执行覆盖恢复
            shutil.copy2(backup_file, db_file)
            messagebox.showinfo("恢复成功", f"✅ 数据库已成功恢复至【{filename}】状态！\n\n(系统已自动生成 failsafe 快照以防万一)\n\n点击确定后系统全局数据将自动刷新。")
            
            # 联动刷新所有模块的数据，无需重启软件
            load_backup_list()
            load_bills_data()
            load_personnel_data()
            draw_native_charts()

        except Exception as e:
            messagebox.showerror("恢复失败", f"执行恢复时发生底层错误：\n{e}")

    # 核心逻辑：删除备份文件
    def delete_backup():
        selected = tree_backup.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在列表中选中一个要删除的备份文件！")
            return
        
        filename = tree_backup.item(selected[0])['values'][0]
        backup_dir = 'backups'
        backup_file = os.path.join(backup_dir, filename)

        if messagebox.askyesno("确认删除", f"确定要永久删除备份文件【{filename}】吗？\n删除后不可找回！"):
            try:
                os.remove(backup_file)
                load_backup_list()
            except Exception as e:
                messagebox.showerror("删除失败", f"无法删除文件：{e}")

    # 底部操作按钮区
    bottom_backup_btn_frame = tk.Frame(tab_backup, bg=bg_color)
    bottom_backup_btn_frame.pack(pady=(0, 20))

    tk.Button(bottom_backup_btn_frame, text="➕ 新建手动备份", font=("微软雅黑", 11, "bold"), bg="#d9f2d9", fg="#2e7d32", padx=20, command=manual_backup).pack(side=tk.LEFT, padx=15)
    tk.Button(bottom_backup_btn_frame, text="↩️ 恢复选中备份", font=("微软雅黑", 11, "bold"), bg="#ffcc99", fg="#d84315", padx=20, command=restore_backup).pack(side=tk.LEFT, padx=15)
    tk.Button(bottom_backup_btn_frame, text="🗑️ 删除选中备份", font=("微软雅黑", 10), bg="#ffb3b3", fg="#c62828", padx=15, command=delete_backup).pack(side=tk.LEFT, padx=15)
    tk.Button(bottom_backup_btn_frame, text="🔄 刷新列表", font=("微软雅黑", 10), padx=15, command=load_backup_list).pack(side=tk.LEFT, padx=15)

    # 界面初始化时加载一次备份列表
    load_backup_list()


    load_bills_data()
    load_personnel_data()
    root.mainloop()

if __name__ == '__main__':
    start_admin_app()