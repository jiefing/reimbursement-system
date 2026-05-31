import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
import sqlite3
import os
import zipfile

# ================= 0. 数据库辅助功能 =================
def init_database():
    conn = sqlite3.connect('lab_billing_system.db')
    cursor = conn.cursor()
    
    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN note TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN attachment_dir TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE Invoices ADD COLUMN amount REAL")
    except: pass
    try: cursor.execute("ALTER TABLE Reimbursement_Forms ADD COLUMN reimburse_types TEXT")
    except: pass
    
    conn.commit()

    cursor.execute("SELECT count(*) FROM Personnel")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO Personnel (name, title, grade) VALUES ('张三', '测试研究员', '2024级博士')")
        cursor.execute("INSERT INTO Personnel (name, title, grade) VALUES ('李四', '教授', '教师团队')")
        conn.commit()
    conn.close()

def get_all_grades():
    if not os.path.exists('lab_billing_system.db'): return []
    conn = sqlite3.connect('lab_billing_system.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT grade FROM Personnel WHERE grade IS NOT NULL AND grade != ''")
    records = cursor.fetchall()
    conn.close()
    return [row[0] for row in records]

def get_personnel_by_grade(grade_name):
    if not os.path.exists('lab_billing_system.db'): return []
    conn = sqlite3.connect('lab_billing_system.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM Personnel WHERE grade = ?", (grade_name,))
    records = cursor.fetchall()
    conn.close()
    return [f"{row[0]}-{row[1]}" for row in records]

# ================= 1. 核心解析引擎 =================
def extract_info(text):
    yuyue_danhao = re.search(r"预约单号：(\d+)", text)
    yewu_hao = re.search(r"业务号：([A-Za-z0-9]+)", text)
    yuyue_shijian = re.search(r"预约时间：([\d-]+)", text)
    jine_match = re.search(r"￥([\d,\.]+)", text)

    clean_text = re.sub(r"对方账号\s*:\s*\d+", "", text)
    fapiao_list = re.findall(r"\b\d{20}\b", clean_text)
    fapiao_haos = ", ".join(list(set(fapiao_list))) if fapiao_list else "无发票"

    jingfei_hao = ""
    danju_leixing = "未知类型"
    if "日常报销单" in text:
        danju_leixing = "日常报销单"
        jingfei_match = re.search(r"经费号\s+支出内容.*?(\d{4}-[A-Za-z0-9]+)", text, re.DOTALL)
        if jingfei_match: jingfei_hao = jingfei_match.group(1)
    elif "差旅费报销单" in text:
        danju_leixing = "差旅费报销单"
        jingfei_match = re.search(r"经费号：(\d{4}-[A-Za-z0-9]+)", text)
        if jingfei_match: jingfei_hao = jingfei_match.group(1)

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
        "单据类型": danju_leixing, 
        "预约单号": yuyue_danhao.group(1) if yuyue_danhao else "", 
        "业务号": yewu_hao.group(1) if yewu_hao else "",
        "预约时间": yuyue_shijian.group(1) if yuyue_shijian else "", 
        "经费号": jingfei_hao, 
        "总金额": jine_match.group(1) if jine_match else "",
        "发票号": fapiao_haos, 
        "备注": "",
        "智能推断项目": guessed_types
    }

# ================= 2. 图形界面构建 =================
def start_app():
    init_database()

    root = tk.Tk()
    root.title("实验室财务报销归档系统 v1.0")
    root.geometry("1180x800") 
    bg_color = "#F8F8E7" 
    main_font = ("Consolas", 11)
    root.configure(bg=bg_color)

    # ================= 人员库独立弹窗 =================
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

        def add_person():
            name, grade = name_e.get().strip(), grade_e.get().strip()
            if not name or not grade:
                messagebox.showerror("缺少信息", "【姓名】和【年级】是必填项！", parent=p_win)
                return
            conn = sqlite3.connect('lab_billing_system.db')
            c = conn.cursor()
            c.execute('''INSERT INTO Personnel (name, grade, student_id, title, phone, bank_card, note) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                      (name, grade, sid_e.get(), title_e.get(), phone_e.get(), bank_e.get(), note_e.get()))
            conn.commit()
            conn.close()
            for entry in [name_e, grade_e, sid_e, title_e, phone_e, bank_e, note_e]: entry.delete(0, tk.END)
            load_personnel_data()
            messagebox.showinfo("成功", f"人员 {name} 录入成功！", parent=p_win)

        def delete_person():
            selected = tree.selection()
            if not selected: return messagebox.showwarning("提示", "请选中人员！", parent=p_win)
            person_id, person_name = tree.item(selected[0])['values'][0], tree.item(selected[0])['values'][1]
            if messagebox.askyesno("确认删除", f"确定彻底删除【{person_name}】？", parent=p_win):
                conn = sqlite3.connect('lab_billing_system.db')
                conn.cursor().execute("DELETE FROM Personnel WHERE id=?", (person_id,))
                conn.commit(); conn.close()
                load_personnel_data()

        btn_frame = tk.Frame(p_win, bg=bg_color)
        btn_frame.pack(fill=tk.X, padx=10)
        tk.Button(btn_frame, text="➕ 新增/保存人员", bg="#d9f2d9", font=("微软雅黑", 10), command=add_person).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🗑️ 删除选中人员", bg="#ffb3b3", font=("微软雅黑", 10), command=delete_person).pack(side=tk.LEFT, padx=5)
        load_personnel_data()

    # ================= 主界面 =================
    top_nav = tk.Frame(root, bg="#e0e0d1", height=40)
    top_nav.pack(side=tk.TOP, fill=tk.X)
    top_nav.pack_propagate(False) 
    tk.Button(top_nav, text="⚙️ 打开人员库管理", font=("微软雅黑", 10, "bold"), bg="#d9e6f2", command=open_personnel_window).pack(side=tk.LEFT, padx=10, pady=5)

    main_content = tk.Frame(root, bg=bg_color)
    main_content.pack(fill=tk.BOTH, expand=True)

    left_frame = tk.Frame(main_content, bg=bg_color)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    right_frame = tk.Frame(main_content, bg=bg_color)
    right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

    tk.Label(left_frame, text="1. 请在此处粘贴报销单文本：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    text_input = tk.Text(left_frame, width=42, height=28, font=main_font)
    text_input.pack(fill=tk.BOTH, expand=True, pady=5)

    tk.Label(right_frame, text="2. 提取结果确认与编辑：", bg=bg_color, font=main_font).pack(anchor=tk.W, pady=(0, 5))

    top_info_frame = tk.Frame(right_frame, bg=bg_color)
    top_info_frame.pack(fill=tk.X, pady=(0, 10))

    info_left_frame = tk.Frame(top_info_frame, bg=bg_color)
    info_left_frame.pack(side=tk.LEFT, fill=tk.Y)

    info_right_frame = tk.Frame(top_info_frame, bg=bg_color)
    info_right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(20, 0)) 

    # --------- 左侧上半区：基础信息 ---------
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

    # --------- ！！！左侧下半区：报销项目多选区 ！！！ ---------
    types_frame = tk.Frame(info_left_frame, bg=bg_color)
    types_frame.pack(fill=tk.X, pady=(15, 0))
    tk.Label(types_frame, text="报销项目 (可多选)：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    
    cb_container = tk.Frame(types_frame, bg=bg_color)
    cb_container.pack(fill=tk.X)
    
    reimburse_options = ["差旅报销", "办公耗材", "实验耗材", "邮寄服务", 
                         "办公服务", "实验服务", "技术服务", "设备维护", "版面费用", "其他"]
    type_vars = {}
    
    # 画出常规选项的网格 (前10个)
    for i, opt in enumerate(reimburse_options):
        var = tk.BooleanVar()
        type_vars[opt] = var
        cb = tk.Checkbutton(cb_container, text=opt, variable=var, bg=bg_color, font=("微软雅黑", 9))
        cb.grid(row=i//3, column=i%3, sticky=tk.W, padx=2, pady=2)

    # ！！！新增的“自定义选项”！！！
    # 自定义 1
    custom_frame1 = tk.Frame(cb_container, bg=bg_color)
    custom_frame1.grid(row=3, column=1, sticky=tk.W, padx=2, pady=2)
    custom_var1 = tk.BooleanVar()
    tk.Checkbutton(custom_frame1, variable=custom_var1, bg=bg_color).pack(side=tk.LEFT)
    custom_entry1 = tk.Entry(custom_frame1, font=("微软雅黑", 9), width=8)
    custom_entry1.pack(side=tk.LEFT)
    
    # 自定义 2
    custom_frame2 = tk.Frame(cb_container, bg=bg_color)
    custom_frame2.grid(row=3, column=2, sticky=tk.W, padx=2, pady=2)
    custom_var2 = tk.BooleanVar()
    tk.Checkbutton(custom_frame2, variable=custom_var2, bg=bg_color).pack(side=tk.LEFT)
    custom_entry2 = tk.Entry(custom_frame2, font=("微软雅黑", 9), width=8)
    custom_entry2.pack(side=tk.LEFT)

    # --------- 右侧区域：超大备注与附件 ---------
    tk.Label(info_right_frame, text="备注：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    note_text = tk.Text(info_right_frame, height=5, font=main_font, width=30) # 加高了备注框
    note_text.pack(fill=tk.X, pady=(0, 10))
    entries["备注"] = note_text 

    tk.Label(info_right_frame, text="报销附件：", bg=bg_color, font=main_font).pack(anchor=tk.W)
    attach_box_frame = tk.Frame(info_right_frame, bg=bg_color)
    attach_box_frame.pack(fill=tk.BOTH, expand=True)

    attach_listbox = tk.Listbox(attach_box_frame, height=6, font=main_font) # 加高了附件框
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

    # ================= 发票区域 =================
    tk.Label(right_frame, text="发票清单：", bg=bg_color, font=main_font).pack(anchor=tk.W, pady=(10, 0))
    invoice_container = tk.Frame(right_frame, bg=bg_color)
    invoice_container.pack(fill=tk.BOTH, expand=True)
    invoice_frame = tk.Frame(invoice_container, bg=bg_color, bd=1, relief="sunken")
    invoice_frame.pack(fill=tk.BOTH, expand=True, pady=2)

    sum_frame = tk.Frame(right_frame, bg=bg_color)
    sum_frame.pack(fill=tk.X, pady=2)
    sum_label = tk.Label(sum_frame, text="发票合计金额：0.00 元", font=("微软雅黑", 12, "bold"), fg="#d9534f", bg=bg_color)
    sum_label.pack(side=tk.RIGHT, padx=10)

    active_invoice_widgets = []
    
    def update_total_sum(*args):
        total = 0.0
        for w in active_invoice_widgets:
            val = w["amt_entry"].get().strip()
            if val:
                try: total += float(val)
                except ValueError: pass
        sum_label.config(text=f"发票合计金额：{total:.2f} 元")

    def add_invoice_row(invoice_num=""):
        row = tk.Frame(invoice_frame, bg=bg_color)
        row.pack(fill=tk.X, pady=3, padx=5)
        
        fp_entry = tk.Entry(row, font=main_font, width=21)
        fp_entry.insert(0, invoice_num)
        fp_entry.pack(side=tk.LEFT)
        
        tk.Label(row, text=" 金额:", bg=bg_color, font=main_font).pack(side=tk.LEFT)
        amt_entry = tk.Entry(row, font=main_font, width=8)
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
            
        row_widgets = {"row_frame": row, "fp_entry": fp_entry, "amt_entry": amt_entry, "person_cmb": person_cmb}
        active_invoice_widgets.append(row_widgets)

        def delete_this_row():
            active_invoice_widgets.remove(row_widgets) 
            row.destroy()
            update_total_sum()

        tk.Button(row, text="✖ 删除", bg="#ffb3b3", font=("微软雅黑", 8), command=delete_this_row).pack(side=tk.LEFT, padx=5)

    def execute_save_data():
        order_id = entries["预约单号"].get().strip()
        if not order_id:
            messagebox.showerror("保存失败", "【预约单号】不能为空！它是归档的唯一凭证！")
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
        
        # ！！！智能合并选项：将标准勾选项和手写自定义项合并！！！
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
                if person_str and "-" in person_str:
                    person_id = person_str.split("-")[0]

                if fp_num or amt:
                    c.execute('''
                        INSERT INTO Invoices (invoice_num, amount, form_order_id, personnel_id)
                        VALUES (?, ?, ?, ?)
                    ''', (fp_num, amt, order_id, person_id))

            conn.commit()
            conn.close()
            
            success_msg = f"🎉 单号 {order_id} 的数据已入库！\n报销项目：{types_str if types_str else '未选择'}"
            if zip_path:
                success_msg += f"\n📁 附件已压缩归档至：\n{zip_path}"
                
            messagebox.showinfo("大功告成", success_msg)
            
        except Exception as e:
            messagebox.showerror("数据库错误", f"保存出错：\n{e}")

    bottom_btn_frame = tk.Frame(right_frame, bg=bg_color)
    bottom_btn_frame.pack(fill=tk.X, pady=10)

    tk.Button(bottom_btn_frame, text="+ 手动新增发票", bg="#d9f2d9", font=("微软雅黑", 9), command=lambda: add_invoice_row("")).pack(side=tk.LEFT)
    tk.Button(bottom_btn_frame, text="💾 保存并归档入库", bg="#b3d9ff", font=("微软雅黑", 10, "bold"), command=execute_save_data).pack(side=tk.RIGHT)

    def on_extract_btn_click():
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
            if guessed_opt in type_vars:
                type_vars[guessed_opt].set(True)
                
        # 提取新文本时，顺便清空之前的自定义复选框
        custom_var1.set(False); custom_entry1.delete(0, tk.END)
        custom_var2.set(False); custom_entry2.delete(0, tk.END)

        clear_files()
        
        active_invoice_widgets.clear()
        for widget in invoice_frame.winfo_children(): widget.destroy()
        update_total_sum()

        if result["发票号"] and result["发票号"] != "无发票":
            for fp in result["发票号"].split(", "): add_invoice_row(fp) 

    tk.Button(left_frame, text="解析文本 >>", font=("Consolas", 12, "bold"), bg="#d0d0d0", command=on_extract_btn_click).pack(pady=10)
    root.mainloop()

if __name__ == '__main__':
    start_app()