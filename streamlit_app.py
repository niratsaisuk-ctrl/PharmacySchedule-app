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

    model.Maximize(sum(reward_v
