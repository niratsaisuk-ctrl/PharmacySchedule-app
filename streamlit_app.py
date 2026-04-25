import streamlit as st
import pandas as pd
import io
from ortools.sat.python import cp_model

# ==========================================
# ⚙️ ส่วนที่ 1: ฟังก์ชันคำนวณตาราง (AI Logic)
# ==========================================
VALID_TIMES = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00",
               "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]

def time_to_slot(t_str):
    return VALID_TIMES.index(t_str)

def generate_schedule(DAY_OF_WEEK, LEAVES, CUSTOM_TASKS, PART_TIME, FIX_BREAKS):
    model = cp_model.CpModel()
    
    ft_pharmacists = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 
                      'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
    pt_pharmacists = [pt['name'] for pt in PART_TIME]
    all_pharmacists = ft_pharmacists + pt_pharmacists
    
    time_slots = [f"{VALID_TIMES[i]}-{VALID_TIMES[i+1]}" for i in range(len(VALID_TIMES)-1)]
    
    dispensing_tasks = ['จ่ายยา_4', 'จ่ายยา_5', 'จ่ายยา_6', 'จ่ายยา_7', 'จ่ายยา_8', 'จ่ายยา_9', 'จ่ายยา_10', 'จ่ายยา_11']
    ver_cpoe_tasks = ['Ver_1', 'Ver_2', 'Ver_3', 'Ver_4', 'Ver_5', 'Ver_6']
    ver_ps_tasks = ['PS_1', 'PS_2', 'PS_3', 'PS_4', 'PS_5']
    tasks = dispensing_tasks + ver_cpoe_tasks + ver_ps_tasks + ['Match_C', 'Matching', 'พัก', 'งานเฉพาะ', 'ลา', 'นอกเวลา', 'ว่าง']
             
    x = {}
    for p in all_pharmacists:
        for t in range(16):
            for task in tasks:
                x[p, t, task] = model.NewBoolVar(f'x_{p}_{t}_{task}')
                
    for p in all_pharmacists:
        for t in range(16):
            model.AddExactlyOne(x[p, t, task] for task in tasks)

    if DAY_OF_WEEK == 'Wed_Fri':
        break_slots = [6, 7, 8, 9, 10, 11] 
        peak_slots = [3, 4, 12, 13, 14, 15] 
        b_groups = [(6,8), (8,10), (10,12)] 
    else:
        break_slots = [5, 6, 7, 8, 9, 10] 
        peak_slots = [3, 4, 11, 12, 13, 14, 15] 
        b_groups = [(5,7), (7,9), (9,11)]

    # จัดการวันลา
    leave_slots = set()
    for p, l_type in LEAVES.items():
        if l_type == 'ทั้งวัน': l_range = range(0, 16)
        elif l_type == 'เช้า': l_range = range(0, 9)
        elif l_type == 'บ่าย': l_range = range(7, 16)
        for t in l_range: leave_slots.add((p, t))

    for p in all_pharmacists:
        for t in range(16):
            if (p, t) in leave_slots: model.Add(x[p, t, 'ลา'] == 1)
            else: model.Add(x[p, t, 'ลา'] == 0)

    # จัดการงานเฉพาะราย
    custom_dict_index = {}
    for (p, start, end), task_name in CUSTOM_TASKS.items():
        s_idx, e_idx = time_to_slot(start), time_to_slot(end)
        for t in range(s_idx, e_idx):
            model.Add(x[p, t, 'งานเฉพาะ'] == 1)
            custom_dict_index[(p, t)] = task_name
            
    for p in all_pharmacists:
        for t in range(16):
            if (p, t) not in custom_dict_index: model.Add(x[p, t, 'งานเฉพาะ'] == 0)

    # จัดการ Part-time
    pt_dispense_allowed = ['จ่ายยา_7', 'จ่ายยา_8']
    if len(PART_TIME) > 2: pt_dispense_allowed.extend(['จ่ายยา_6', 'จ่ายยา_9'])
    pt_all_allowed = pt_dispense_allowed + ['Matching', 'พัก', 'นอกเวลา']

    for pt in PART_TIME:
        p = pt['name']
        s_idx, e_idx = time_to_slot(pt['start']), time_to_slot(pt['end'])
        work_slots_count = max(0, e_idx - s_idx)
        
        for t in range(16):
            if t < s_idx or t >= e_idx: model.Add(x[p, t, 'นอกเวลา'] == 1)
            else: model.Add(x[p, t, 'นอกเวลา'] == 0)
            model.Add(sum(x[p, t, task] for task in pt_all_allowed) == 1)

        if pt['has_break'] and s_idx <= 8 and e_idx > 8:
            model.Add(x[p, 8, 'พัก'] == 1) 
            if e_idx > 9: model.Add(x[p, 9, 'Matching'] == 1) 
            work_slots_count -= 1 
        
        for t in range(16):
            if not (pt['has_break'] and t == 8): model.Add(x[p, t, 'พัก'] == 0)

        hours = work_slots_count / 2.0
        disp_vars_7 = [x[p, t, 'จ่ายยา_7'] for t in range(max(0, s_idx), min(16, e_idx))]
        disp_vars_8 = [x[p, t, 'จ่ายยา_8'] for t in range(max(0, s_idx), min(16, e_idx))]
        all_disp_vars = []
        for d_task in pt_dispense_allowed:
            all_disp_vars.extend([x[p, t, d_task] for t in range(max(0, s_idx), min(16, e_idx))])
        
        if hours > 0:
            if hours <= 4.0:
                model.Add(sum(disp_vars_7) == 2)
                model.Add(sum(disp_vars_8) == 2)
                model.Add(sum(all_disp_vars) == 4) 
            elif hours <= 5.0:
                model.Add(sum(disp_vars_7) + sum(disp_vars_8) == 6)
                model.Add(sum(disp_vars_7) >= 2)
                model.Add(sum(disp_vars_8) >= 2)
                model.Add(sum(all_disp_vars) == 6) 
            else:
                model.Add(sum(disp_vars_7) + sum(disp_vars_8) == 8)
                model.Add(sum(disp_vars_7) >= 2)
                model.Add(sum(disp_vars_8) >= 2)
                model.Add(sum(all_disp_vars) == 8) 

        for t in range(max(0, s_idx), min(16, e_idx)):
            if not (pt['has_break'] and t == 8):
                is_dispensing = model.NewBoolVar(f'is_dispensing_{p}_{t}')
                model.Add(sum(x[p, t, task] for task in pt_dispense_allowed) == 1).OnlyEnforceIf(is_dispensing)
                model.Add(sum(x[p, t, task] for task in pt_dispense_allowed) == 0).OnlyEnforceIf(is_dispensing.Not())
                model.Add(x[p, t, 'Matching'] == 1).OnlyEnforceIf(is_dispensing.Not())

    # กฎ Full-Time
    for p in ft_pharmacists:
        model.Add(sum(x[p, t, 'นอกเวลา'] for t in range(16)) == 0) 
        
        for t in range(16): model.Add(x[p, t, 'Matching'] == 0)
        
        if p not in LEAVES:
            model.Add(sum(x[p, t, 'พัก'] for t in range(16)) == 2)
            b1 = model.NewBoolVar(f'b1_{p}') 
            b2 = model.NewBoolVar(f'b2_{p}') 
            b3 = model.NewBoolVar(f'b3_{p}') 
            
            if p in FIX_BREAKS:
                req_b = FIX_BREAKS[p]
                if req_b == 0: model.Add(b1 == 1); model.Add(b2 == 0); model.Add(b3 == 0)
                elif req_b == 1: model.Add(b1 == 0); model.Add(b2 == 1); model.Add(b3 == 0)
                elif req_b == 2: model.Add(b1 == 0); model.Add(b2 == 0); model.Add(b3 == 1)
            else:
                model.AddExactlyOne([b1, b2, b3]) 
            
            for t in range(*b_groups[0]): model.Add(x[p, t, 'พัก'] == 1).OnlyEnforceIf(b1)
            for t in range(*b_groups[1]): model.Add(x[p, t, 'พัก'] == 1).OnlyEnforceIf(b2)
            for t in range(*b_groups[2]): model.Add(x[p, t, 'พัก'] == 1).OnlyEnforceIf(b3)
        else:
            model.Add(sum(x[p, t, 'พัก'] for t in range(16)) == 0)

        for t in range(16):
            if t not in break_slots: model.Add(x[p, t, 'พัก'] == 0)

    # Mandatory Constraints
    for t in range(16):
        for task in tasks:
            if task not in ['พัก', 'งานเฉพาะ', 'ลา', 'นอกเวลา', 'ว่าง', 'Matching']:
                model.Add(sum(x[p, t, task] for p in all_pharmacists) <= 1)

        if t < 2: req_dispense = ['จ่ายยา_6', 'จ่ายยา_7', 'จ่ายยา_8', 'จ่ายยา_9']
        else: req_dispense = ['จ่ายยา_5', 'จ่ายยา_6', 'จ่ายยา_7', 'จ่ายยา_8', 'จ่ายยา_9', 'จ่ายยา_10']
            
        for task in req_dispense + ['Ver_1', 'Ver_2', 'Ver_3', 'PS_1', 'Match_C']:
            model.Add(sum(x[p, t, task] for p in all_pharmacists) == 1)
            
        if t not in break_slots:
            model.Add(sum(x[p, t, 'PS_2'] for p in all_pharmacists) == 1)
        else:
            model.Add(sum(x[p, t, 'PS_2'] for p in all_pharmacists) <= 1)

    categories_to_prevent_internal_switch = [dispensing_tasks, ver_cpoe_tasks, ver_ps_tasks]
    work_categories = [dispensing_tasks, ver_cpoe_tasks, ver_ps_tasks, ['Match_C'], ['Matching']]

    for p in all_pharmacists:
        for t in range(15):
            for cat in categories_to_prevent_internal_switch:
                for task1 in cat:
                    for task2 in cat:
                        if task1 != task2: model.AddImplication(x[p, t, task1], x[p, t+1, task2].Not())
                            
        for cat in work_categories:
            for t in range(14):
                model.Add(sum(x[p, t, task] + x[p, t+1, task] + x[p, t+2, task] for task in cat) <= 2)

    for p in ft_pharmacists:
        model.Add(sum(x[p, t, task] for t in range(16) for task in dispensing_tasks) <= 6)
        b_7 = model.NewBoolVar(f'b_7_{p}')
        b_8 = model.NewBoolVar(f'b_8_{p}')
        model.Add(sum(x[p, t, 'จ่ายยา_7'] for t in range(16)) <= 2 * b_7)
        model.Add(sum(x[p, t, 'จ่ายยา_8'] for t in range(16)) <= 2 * b_8)
        model.Add(b_7 + b_8 <= 1)
        
        for v in ['Ver_1', 'Ver_2', 'Ver_3', 'Match_C']:
            model.Add(sum(x[p, t, v] for t in range(16)) <= 2)

    # Scoring
    reward_vars = []
    for p in all_pharmacists:
        for t in range(15):
            for task in tasks:
                if task in ['พัก', 'งานเฉพาะ', 'ลา', 'นอกเวลา', 'ว่าง']: continue
                match_var = model.NewBoolVar(f'match_{p}_{t}_{task}')
                model.AddImplication(match_var, x[p, t, task])
                model.AddImplication(match_var, x[p, t+1, task])
                reward_vars.append(match_var * 50000)

    for t in range(16):
        if t in peak_slots: 
            weights = {'จ่ายยา_4': 8000, 'จ่ายยา_11': 7000, 'Ver_4': 6000, 'PS_3': 5000, 'PS_4': 4000, 'Ver_5': 3000, 'PS_5': 2000, 'Ver_6': 1000}
        else: 
            weights = {'Ver_4': 8000, 'PS_3': 7000, 'PS_4': 6000, 'Ver_5': 5000, 'PS_5': 4000, 'Ver_6': 3000, 'จ่ายยา_4': 2000, 'จ่ายยา_11': 1000}

        if t in break_slots: weights['PS_2'] = 10000 
            
        for task, weight in weights.items():
            for p in all_pharmacists: reward_vars.append(x[p, t, task] * weight)
                
    for p in ft_pharmacists:
        for t in range(16): reward_vars.append(x[p, t, 'ว่าง'] * -5000)

    model.Maximize(sum(reward_vars))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120.0 

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        for p in all_pharmacists:
            row_data = {'ชื่อเภสัชกร': p}
            for t in range(16):
                for task in tasks:
                    if solver.Value(x[p, t, task]) == 1:
                        if task == 'งานเฉพาะ': display_task = custom_dict_index.get((p, t), 'งานเฉพาะ')
                        elif task in ['นอกเวลา', 'ว่าง']: display_task = '-'
                        elif task == 'Match_C': display_task = 'Match + C'
                        elif task == 'Matching': display_task = 'Matching'
                        elif task == 'Ver_1': display_task = 'Ver 1 INC'
                        elif task == 'Ver_2': display_task = 'Ver 2/ปณ.'
                        elif task == 'Ver_3': display_task = 'Ver 3/A'
                        elif task.startswith('PS_'): display_task = 'Ver ' + task.replace('_', '')
                        else: display_task = task.replace('_', ' ')
                        row_data[time_slots[t]] = display_task
            schedule_data.append(row_data)
        return pd.DataFrame(schedule_data), "Success"
    else:
        return None, "Infeasible"


# ==========================================
# 🖥️ ส่วนที่ 2: สร้างหน้าเว็บ UI ด้วย Streamlit
# ==========================================
st.set_page_config(page_title="Pharmacy Schedule App", layout="wide", page_icon="💊")

st.title("💊 โปรแกรมจัดตารางเภสัชกรห้องยาอัจฉริยะ")
st.markdown("ระบบ AI จัดตารางเวรให้สมดุลอัตโนมัติ กรุณาตั้งค่าทางเมนูด้านซ้าย และกดปุ่มสร้างตารางด้านล่าง")

ft_pharmacists_list = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 
                      'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
dropdown_names = ["ไม่มี"] + ft_pharmacists_list

# เก็บค่าตัวแปรจาก Sidebar
leaves_input = {}
pt_input = []
custom_tasks_input = {}
fix_breaks_input = {}
DAY_OF_WEEK = 'Normal'

with st.sidebar:
    st.header("⚙️ ตั้งค่าตารางประจำวัน")
    
    # 1. ประเภทวัน
    day_type = st.radio("📅 เลือกประเภทวัน", ["ปกติ (จ,อ,พฤ)", "พุธ หรือ ศุกร์ (ปรับเวลาพัก)"])
    DAY_OF_WEEK = 'Wed_Fri' if day_type == "พุธ หรือ ศุกร์ (ปรับเวลาพัก)" else 'Normal'
    st.divider()
    
    # 2. คนลา
    st.subheader("🏖️ ผู้ที่ลาในวันนี้ (สูงสุด 4 คน)")
    for i in range(4):
        c1, c2 = st.columns([3, 2])
        with c1: p_leave = st.selectbox(f"คนที่ {i+1}", dropdown_names, key=f"l_name_{i}")
        with c2: t_leave = st.selectbox("ประเภท", ["ทั้งวัน", "เช้า", "บ่าย"], key=f"l_type_{i}")
        if p_leave != "ไม่มี": leaves_input[p_leave] = t_leave

    st.divider()

    # 3. Part-time
    st.subheader("🧑‍⚕️ เภสัชกร Part-time (สูงสุด 3 คน)")
    for i in range(3):
        with st.expander(f"Part-time คนที่ {i+1}"):
            pt_name = st.text_input("ชื่อ PT", key=f"pt_n_{i}")
            c1, c2 = st.columns(2)
            with c1: pt_s = st.selectbox("เริ่ม", VALID_TIMES, index=0, key=f"pt_s_{i}")
            with c2: pt_e = st.selectbox("สิ้นสุด", VALID_TIMES, index=16, key=f"pt_e_{i}")
            pt_b = st.checkbox("จัดพัก 12.30-13.00", value=True, key=f"pt_b_{i}")
            
            if pt_name.strip() != "":
                if VALID_TIMES.index(pt_s) < VALID_TIMES.index(pt_e):
                    pt_input.append({'name': pt_name, 'start': pt_s, 'end': pt_e, 'has_break': pt_b})
                else:
                    st.error("เวลาผิดพลาด")

    st.divider()

    # 4. งานเฉพาะราย
    st.subheader("📋 ภารกิจพิเศษ / งานเฉพาะราย (สูงสุด 20 งาน)")
    st.caption("เว้นว่างไว้หากไม่มีภารกิจ")
    for i in range(20):
        with st.expander(f"งานที่ {i+1}"):
            p_task = st.selectbox(f"ชื่อคน", dropdown_names, key=f"t_name_{i}")
            n_task = st.text_input(f"ชื่องาน", key=f"t_n_{i}")
            c1, c2 = st.columns(2)
            with c1: s_task = st.selectbox(f"เริ่ม", VALID_TIMES, index=0, key=f"t_s_{i}")
            with c2: e_task = st.selectbox(f"สิ้นสุด", VALID_TIMES, index=2, key=f"t_e_{i}")
            
            if p_task != "ไม่มี" and n_task.strip() != "":
                if VALID_TIMES.index(s_task) < VALID_TIMES.index(e_task):
                    custom_tasks_input[(p_task, s_task, e_task)] = n_task.strip()

    st.divider()

    # 5. Fix พัก
    st.subheader("🍱 ล็อกเวลาพักเฉพาะบุคคล (สูงสุด 5 คน)")
    break_choices = ["รอบที่ 1 (11.00 หรือ 11.30)", "รอบที่ 2 (12.00 หรือ 12.30)", "รอบที่ 3 (13.00 หรือ 13.30)"]
    for i in range(5):
        c1, c2 = st.columns([2, 3])
        with c1: p_b = st.selectbox(f"คนที่ {i+1}", dropdown_names, key=f"b_name_{i}")
        with c2: t_b = st.selectbox("รอบพัก", break_choices, key=f"b_time_{i}")
        if p_b != "ไม่มี":
            if "รอบที่ 1" in t_b: fix_breaks_input[p_b] = 0
            elif "รอบที่ 2" in t_b: fix_breaks_input[p_b] = 1
            elif "รอบที่ 3" in t_b: fix_breaks_input[p_b] = 2

# ปุ่มรันระบบ (Main Area)
st.divider()
if st.button("🚀 สร้างตารางปฏิบัติงาน (คลิก)", type="primary", use_container_width=True):
    with st.spinner('🤖 AI กำลังประมวลผลความเป็นไปได้นับล้านรูปแบบ... โปรดรอ 1-2 นาที'):
        try:
            df_result, status = generate_schedule(DAY_OF_WEEK, leaves_input, custom_tasks_input, pt_input, fix_breaks_input)
            
            if status == "Success":
                st.success("🎉 สร้างตารางเสร็จสมบูรณ์!")
                st.dataframe(df_result, use_container_width=True)
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_result.to_excel(writer, index=False, sheet_name='Schedule')
                
                st.download_button(
                    label="📥 ดาวน์โหลดตารางเป็นไฟล์ Excel",
                    data=buffer.getvalue(),
                    file_name="Pharmacy_Schedule_App.xlsx",
                    mime="application/vnd.ms-excel",
                    use_container_width=True
                )
            else:
                st.error("⚠️ Infeasible: ไม่สามารถจัดตารางได้! (คนไม่พอ, ช่วงเวลางานพิเศษชนกัน หรือล็อกเวลาพักซ้อนกันมากไป) ลองลดเงื่อนไขทางด้านซ้ายลงครับ")
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในระบบ: {str(e)}")
