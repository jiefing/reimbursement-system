# 华南农业大学动物繁殖实验室405报账系统 — Bug 修复报告

**修复日期**：2026-05-29  
**修复版本**：v1.31 → v1.32  
**修复文件**：`main.py`  
**修复人**：Claude（基于贾腾飞的 bug 报告）

---

## 一、Bug #1：批量设置所属人功能无效

### 现象

点击 "⚙️ 批量设置所属人" → 弹窗出现 → 选择行、年级、人员 → 点击 "✅ 应用设置" → 弹窗关闭并提示"完成"，但主窗口中对应发票行的**年级和人员完全没有被更新**。

此 bug 在连续 3 次迭代修复后仍未解决。

### 根因分析

问题出在两个位置的数据结构不一致：

**位置 ①**：`add_invoice_row()`（第 921 行），发票行的控件字典构建代码：

```python
# 修复前
row_widgets = {
    "row_frame": row,
    "fp_entry": fp_entry,
    "amt_entry": amt_entry,
    "person_cmb": person_cmb    # ← 只有 4 个 key，缺少 grade_cmb！
}
```

年级 Combobox 对象 `grade_cmb` 虽然在代码中创建了（第 899 行），但**没有被放入字典**。

**位置 ②**：`batch_set_person()` 内部的 `_apply()` 函数（第 852 行）：

```python
w["grade_cmb"].set(tg)   # ← 抛出 KeyError: 'grade_cmb'
```

由于 `row_widgets` 字典中不存在 `"grade_cmb"` 这个 key，执行该行代码时抛出 `KeyError` 异常。Tkinter 的事件回调机制会**静默吞掉**该异常——弹窗照常关闭、提示"完成"，但更新逻辑实际上在中途崩溃，导致年级和人员均未更新。

**调用链路**：

```
用户点击 "✅ 应用设置"
  → _apply() 执行
    → for i in selected_indices:
        → w["grade_cmb"].set(tg)     ← KeyError 在此抛出
        → 后续所有代码被跳过
  → popup.destroy()                   ← 弹窗关闭
  → messagebox.showinfo("完成", ...)  ← 误导性提示
```

### 修复方式

**修改位置**：`add_invoice_row()` 中 `row_widgets` 字典（第 927 行）

```python
# 修复后
row_widgets = {
    "row_frame": row,
    "fp_entry": fp_entry,
    "amt_entry": amt_entry,
    "grade_cmb": grade_cmb,     # ← 新增
    "person_cmb": person_cmb,
}
```

---

## 二、Bug #2：`_apply()` 缺少异常处理

### 现象

与 Bug #1 关联。由于缺少异常处理，任何在批量设置循环中发生的错误（如 KeyError、索引越界等）都会被 Tkinter 静默吞掉，用户看到"完成"提示但数据未更新，无法得知发生了什么。

### 根因分析

`_apply()` 函数中设置年级和人员的循环没有任何 `try-except` 保护。在 GUI 框架中，事件回调中的未捕获异常通常不会弹出错误对话框，而是被框架内部捕获并丢弃。

### 修复方式

**修改位置**：`batch_set_person()` 内部的 `_apply()` 函数（第 851-871 行）

```python
# 修复后
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
```

改进点：
- 循环体整体包裹 `try-except`，单行失败不影响其他行
- 增加 `success_count` 计数器，完成消息中如实报告成功/总数（如"已设置 3/5 行"）
- 错误信息通过 `print()` 输出到控制台，便于调试

---

## 三、Bug #3：窗口较小时右侧模块不显示

### 现象

当程序窗口尺寸较小时，右侧面板底部的模块（发票清单区域、合计金额、保存按钮等）会完全不可见。用户**必须手动拖大窗口**才能看到和使用这些功能。

### 根因分析

主窗口初始尺寸为 `1180×800`，但**没有设置最小尺寸限制**，用户可以自由将窗口缩到任意小。

右侧面板 (`right_frame`) 采用垂直堆叠布局，包含以下固定高度组件：

| 组件 | 修复前高度（估算） |
|------|-------------------|
| 标题标签 "提取结果确认与编辑" | ~25px |
| 基础信息区（6 个输入行） | ~170px |
| 报销项目复选框（4 行） | ~120px |
| 备注文本框 | ~100px（height=5） |
| 附件列表框 | ~120px（height=6） |
| "发票清单" 标签 | ~25px |
| 批量设置按钮 | ~30px |
| 发票画布 | ~400px（height=400） |
| 合计金额标签 | ~30px |
| 底部按钮栏 | ~50px |
| **合计** | **~1070px** |

可用垂直空间约为 `800px（窗口高）− 40px（顶部导航栏）= 760px`。固定内容总高度（~1070px）远超可用空间（~760px），即使发票画布设置了 `expand=True` 可伸缩，在极端缩小窗口时，所有可伸缩空间耗尽后，**底部组件仍会被裁剪到屏幕下方**。

### 修复方式

共 5 处改动，将固定高度需求压缩约 280px，并设置最小窗口尺寸：

| 改动 | 位置 | 修复前 | 修复后 | 压缩量 |
|------|------|--------|--------|--------|
| 设置窗口最小尺寸 | 第 223 行 | *(无)* | `root.minsize(1000, 720)` | — |
| 左侧文本输入框高度 | 第 610 行 | `height=28` | `height=24` | ~80px |
| 备注文本框高度 | 第 683 行 | `height=5` | `height=3` | ~40px |
| 附件列表框高度 | 第 691 行 | `height=6` | `height=4` | ~40px |
| 发票画布初始高度 | 第 720 行 | `height=400` | `height=220` | ~180px |

修复后的固定内容高度约 **~790px**，在最小窗口 720px 高度下（可用 ~680px），配合发票画布的 `expand=True` 自动伸缩机制，所有模块均能正常显示。

`minsize(1000, 720)` 确保：
- **宽度** ≥ 1000px：左右两栏均有足够空间显示所有输入控件
- **高度** ≥ 720px：所有垂直堆叠的模块不会溢出可视区域

---

## 修改文件清单

| 文件 | 修改行数 | 说明 |
|------|----------|------|
| `main.py:223` | +1 | 新增 `root.minsize(1000, 720)` |
| `main.py:610` | 1 处修改 | `text_input` 高度 28→24 |
| `main.py:683` | 1 处修改 | `note_text` 高度 5→3 |
| `main.py:691` | 1 处修改 | `attach_listbox` 高度 6→4 |
| `main.py:720` | 1 处修改 | `invoice_canvas` 高度 400→220 |
| `main.py:851-871` | ~10 行重构 | `_apply()` 增加 try-except + success_count |
| `main.py:927` | 1 处修改 | `row_widgets` 新增 `"grade_cmb"` key |

**总计**：1 个文件，7 处修改。

---

## 测试建议

1. **批量设置功能**：
   - 粘贴报销单文本 → 点击"解析文本" → 点击"⚙️ 批量设置所属人"
   - 在弹窗中按住 Ctrl 多选发票行 → 选择年级和人员 → 点击"✅ 应用设置"
   - 验证主窗口中对应行的**年级和人员下拉框均已更新**
   - 验证完成消息显示的成功计数正确（如"已设置 3/3 行"）

2. **窗口缩放**：
   - 将窗口缩小到 1000×720（最小限制），验证所有模块可见
   - 将窗口拖大到全屏，验证布局正常
   - 反复缩放窗口，验证无控件重叠或消失

3. **发票合计金额**：
   - 批量设置人员后，验证发票合计金额自动重新计算（`update_total_sum()` 会在批量设置后触发）
