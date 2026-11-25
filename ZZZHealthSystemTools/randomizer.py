import os
import re
import traceback
from datetime import datetime
from collections import defaultdict
import shutil

def read_ini_file(filename):
    for enc in ('utf-8', 'cp1251'):
        try:
            with open(filename, 'r', encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()

def write_ini_file(filename, lines):
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def generate_randomizer_code(variables, base_interval):
    constants_code = "; === AUTO-GENERATED RANDOMIZER ===\n"
    constants_code += "global $last_switch_time = 0\n"
    constants_code += f"global $switch_interval = {base_interval}\n"

    custom_intervals = {}
    for _, _, interval_name, timer_name, interval_value in variables:
        if interval_name != "$switch_interval":
            custom_intervals[interval_name] = (timer_name, interval_value)

    def interval_num(name):
        try: return int(name.split('_')[-1])
        except ValueError: return 0

    for interval_name in sorted(custom_intervals.keys(), key=interval_num):
        timer_name, interval_value = custom_intervals[interval_name]
        constants_code += f"global {timer_name} = 0\n"
        constants_code += f"global {interval_name} = {interval_value}\n"

    for var_name, values, _, _, _ in variables:
        clean_name = var_name[1:]
        constants_code += f"global $last_{clean_name} = {values[0]}\n"

    groups = defaultdict(list)
    for var_name, values, interval_name, timer_name, _ in variables:
        groups[(interval_name, timer_name)].append((var_name, values))

    present_code = "; === AUTO-GENERATED RANDOMIZER ===\n"

    for (interval_name, timer_name), group_vars in groups.items():
        present_code += f"if time >= {timer_name} + {interval_name}\n"
        present_code += f"    {timer_name} = time\n\n"

        for var_name, values in group_vars:
            clean_name = var_name[1:]
            present_code += f"    ; Для {var_name}: используем только {values}\n"

            if len(values) == 1:
                present_code += f"    $last_{clean_name} = {values[0]}\n"
            else:
                present_code += f"    $last_{clean_name} = $last_{clean_name} + 1\n"
                all_values_set = set(values)
                max_val = max(values)
                current = 0
                while current <= max_val:
                    if current not in all_values_set:
                        next_valid = None
                        for v in sorted(all_values_set):
                            if v > current:
                                next_valid = v
                                break
                        if next_valid is None:
                            next_valid = min(all_values_set)
                        present_code += f"    if $last_{clean_name} == {current}\n"
                        present_code += f"        $last_{clean_name} = {next_valid}\n"
                        present_code += f"    endif\n"
                    current += 1
                present_code += f"    if $last_{clean_name} > {max_val}\n"
                present_code += f"        $last_{clean_name} = {min(values)}\n"
                present_code += f"    endif\n"

            present_code += f"    {var_name} = $last_{clean_name}\n\n"

        present_code += "endif\n\n"

    return constants_code, present_code

def add_code_to_ini(ini_filename, constants_code, present_code):
    lines = read_ini_file(ini_filename)

    present_index = -1
    for i, line in enumerate(lines):
        if line.strip().lower() == '[present]':
            present_index = i
            break

    if present_index != -1:
        lines.insert(present_index + 1, '\n' + present_code + '\n')
    else:
        lines.append('\n[Present]\n')
        lines.append(present_code + '\n')

    constants_index = -1
    for i, line in enumerate(lines):
        if line.strip().lower() == '[constants]':
            constants_index = i
            break

    if constants_index != -1:
        constants_end = constants_index + 1
        while (constants_end < len(lines) and not lines[constants_end].strip().startswith('[')):
            constants_end += 1
        lines.insert(constants_end, '\n' + constants_code + '\n')
    else:
        lines.append('\n[Constants]\n')
        lines.append(constants_code + '\n')

    write_ini_file(ini_filename, lines)

def process_randomizer(mod_dir, ini_filename, base_interval, variables, log_func=print, L=None):
    if L is None: L = {}
    original_dir = os.getcwd()
    
    try:
        os.chdir(mod_dir)
    except Exception as e:
        log_func(f"[ERROR] Не удалось перейти в папку мода '{mod_dir}': {e}")
        return False
    
    try:
        full_path = os.path.join(mod_dir, ini_filename)
        if not os.path.exists(full_path):
            log_func(L.get("log_rand_error_file_not_found", "Error: file {} not found.").format(ini_filename))
            return False

        backup_filename = f"{ini_filename}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(full_path, backup_filename)
        log_func(L.get("log_rand_backup_created", "Backup created: {}").format(backup_filename))

        existing_lines = read_ini_file(full_path)
        existing_blocks = sum(1 for line in existing_lines if 'AUTO-GENERATED RANDOMIZER' in line)
        if existing_blocks > 0:
            log_func(L.get("log_rand_existing_blocks_warning", "⚠ WARNING: file already contains {} randomizer block(s).").format(existing_blocks))

        constants_code, present_code = generate_randomizer_code(variables, base_interval)
        add_code_to_ini(full_path, constants_code, present_code)
        
        log_func(L.get("log_rand_success", "✓ Randomizer successfully added to {}!").format(ini_filename))
        return True
        
    except Exception as e:
        log_func(L.get("log_rand_error_generic", "ERROR during randomizer: {}").format(e))
        log_func(traceback.format_exc())
        return False
    finally:
        try:
            os.chdir(original_dir)
        except Exception:
            pass