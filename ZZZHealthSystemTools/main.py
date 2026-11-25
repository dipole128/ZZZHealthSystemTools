import os
import sys
import subprocess
import json
import re
import shutil
import zipfile
import py7zr
import threading
import glob
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import health_system 
import merger
import randomizer
import ctypes

try:
    # Уникальный ID (можно назвать как угодно)
    myappid = 'HealthSystem.mod.processor.1.0' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass
CONFIG_FILE = "config.json"

def resource_path(relative_path):
    """ Возвращает правильный путь к файлу, работает и в .py, и в .exe """
    try:
        # PyInstaller создает временную папку и сохраняет путь в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
    
def get_available_languages():
    """Ищет все файлы lang_*.json и возвращает словарь {Название: Имя_файла}"""
    languages = {}
    for file in glob.glob("lang_*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                lang_name = data.get("language_name", file)
                languages[lang_name] = file
        except Exception:
            pass
    return languages

def get_current_language_file():
    """Читает выбранный язык из config.json, иначе берет lang_ru.json"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("language_file", "lang_ru.json")
    except Exception:
        pass
    return "lang_ru.json"

def load_lang(lang_file):
    if os.path.exists(lang_file):
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {lang_file}: {e}")
    return {}

# Загружаем текущий язык
CURRENT_LANG_FILE = get_current_language_file()
L = load_lang(CURRENT_LANG_FILE)

# ... (дальше идут ваши глобальные переменные: migoto_path, mod_path и т.д.)

# --- ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И НАСТРОЙКИ ---
CONFIG_FILE = "config.json"
migoto_path = ""
mod_path = ""
mod_dir_global = ""

saved_presets = [] 
found_ini_paths = [] 
active_presets_step1 = []    
variable_vars = {}     

active_presets_step2 = []       
current_outfit_num = 1    
current_step_num = 1      
outfit_buffer = []        

checkbox_vars = {} 
added_random_vars = [] 
randomizer_checkbox_vars = {} 

try:
    import rarfile
    SEVENZIP_PATH = r"C:\Program Files\7-Zip\7z.exe"
    if os.path.exists(SEVENZIP_PATH):
        rarfile.SEVENZIP_TOOL = SEVENZIP_PATH
except ImportError:
    rarfile = None

def load_global_paths():
    global migoto_path, mod_path, mod_dir_global
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                migoto_path = config.get("migoto_path", "")
                mod_path = config.get("mod_path", "")
                mod_dir_global = mod_path
    except Exception:
        pass

def load_config(key):
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get(key)
        return None
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_file_read_error", "Could not read {}: {}").format(CONFIG_FILE, e))
        return None

def update_config(key, value):
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        config[key] = value
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        load_global_paths()
        return True
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_file_save_error", "Could not save to {}: {}").format(CONFIG_FILE, e))
        return False

def get_ini_files_in_mod():
    if not mod_dir_global: return []
    relative_files = []
    try:
        for root, dirs, files in os.walk(mod_dir_global):
            for file in files:
                if file.lower().endswith('.ini') and not file.startswith('DISABLED_'):
                    full_path = os.path.join(root, file)
                    rel = os.path.relpath(full_path, mod_dir_global)
                    relative_files.append(rel)
        return sorted(relative_files)
    except Exception:
        return []

# ==========================================
# ВКЛАДКА 1
# ==========================================
def browse_migoto_folder():
    selected_dir = filedialog.askdirectory()
    if selected_dir:
        path_entry.delete(0, tk.END)
        path_entry.insert(0, selected_dir)

def save_migoto_path():
    path = path_entry.get().strip()
    if not path:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_enter_path", "Please specify a path."))
        return
    if update_config("migoto_path", path):
        messagebox.showinfo(L.get("msg_success", "Успех"), L.get("msg_path_saved", "3dmigoto path saved!"))

def handle_select_archive():
    filetypes = [(L.get("filter_archives", "Archive files"), "*.zip *.rar *.7z"), (L.get("filter_all_files", "All files"), "*.*")]
    
    # Получаем последний сохраненный путь, если он есть
    last_dir = load_config("last_import_dir") or ""
    
    # Передаем initialdir в диалоговое окно
    archive_path = filedialog.askopenfilename(title=L.get("dialog_select_archive", "Select Mod Archive"), filetypes=filetypes, initialdir=last_dir)
    if not archive_path: return
    
    # Сохраняем папку, из которой был выбран архив
    update_config("last_import_dir", os.path.dirname(archive_path))
    
    base_name = os.path.splitext(os.path.basename(archive_path))[0]
    if not migoto_path: 
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_save_migoto_first", "Сначала сохраните путь к 3dmigoto!"))
        return
    
    destination_dir = os.path.join(migoto_path, "Mods", base_name)
    
    try:
        os.makedirs(destination_dir, exist_ok=True)
        ext = os.path.splitext(archive_path)[1].lower()
        
        if ext == ".zip":
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(destination_dir)
        elif ext == ".rar":
            if rarfile is None: return
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(destination_dir)
        elif ext == ".7z":
            if py7zr is None: return
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                archive.extractall(path=destination_dir)
        
        update_config("mod_path", destination_dir)
        reset_outfit_session()
        messagebox.showinfo(L.get("msg_success", "Успех"), L.get("msg_archive_extracted", "Archive extracted to:\n{}").format(destination_dir))
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_error_generic", "Error: {}").format(e))
        
def handle_select_folder():
    # Получаем последний сохраненный путь
    last_dir = load_config("last_import_dir") or ""
    
    # Передаем initialdir в диалоговое окно
    source_dir = filedialog.askdirectory(title=L.get("dialog_select_folder", "Select Mod Folder to Copy"), initialdir=last_dir)
    if not source_dir: return
    
    # Сохраняем родительскую папку (чтобы в следующий раз открылась та же директория)
    update_config("last_import_dir", os.path.dirname(source_dir))
    
    folder_name = os.path.basename(source_dir.rstrip('/\\'))
    if not migoto_path: return
    
    destination_dir = os.path.join(migoto_path, "Mods", folder_name)
    
    try:
        if os.path.exists(destination_dir):
            shutil.rmtree(destination_dir)
        shutil.copytree(source_dir, destination_dir)
        update_config("mod_path", destination_dir)
        reset_outfit_session()
        messagebox.showinfo(L.get("msg_success", "Успех"), L.get("msg_folder_copied", "Folder copied to:\n{}").format(destination_dir))
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_error_generic", "Error: {}").format(e))
        
def scan_for_ini_file():
    global found_ini_paths
    found_ini_paths.clear()

    saved_mod = load_config("mod_path")
    saved_migoto = load_config("migoto_path")
    
    initial_dir = ""
    
    # 1. Проверяем путь к моду (он в приоритете)
    if saved_mod:
        # normpath исправляет смешанные слеши (D:/.../...)
        norm_mod = os.path.normpath(saved_mod)
        if os.path.exists(norm_mod):
            initial_dir = norm_mod
    
    # 2. Если папки мода нет, проверяем путь к 3dmigoto и папку Mods
    if not initial_dir and saved_migoto:
        norm_migoto = os.path.normpath(saved_migoto)
        mods_folder = os.path.join(norm_migoto, "Mods")
        
        if os.path.exists(mods_folder):
            initial_dir = mods_folder
        elif os.path.exists(norm_migoto):
            initial_dir = norm_migoto

    directory_path = filedialog.askdirectory(title=L.get("dialog_scan_dir", "Select Directory to Scan"), initialdir=initial_dir)
    if not directory_path: return
    update_config("mod_path", directory_path)     
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.ini'):
                found_ini_paths.append(os.path.join(root, file))
         
    if found_ini_paths:
        relative_paths = [os.path.relpath(f, directory_path) for f in found_ini_paths]
        ini_combobox['values'] = relative_paths
        ini_combobox.current(0) 
        load_selected_ini()
    else:
        ini_combobox['values'] = []
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_no_ini_found", "No .ini files found."))

def load_selected_ini(event=None):
    global saved_presets, found_ini_paths, variable_vars
    
    idx = ini_combobox.current()
    if idx < 0 or idx >= len(found_ini_paths): return
    
    full_path = found_ini_paths[idx]
    lbl_full_ini_path.config(text=f"{L.get('full_path_label', 'Полный путь:')} {full_path}")
    saved_presets.clear()
    variable_vars.clear()
    
    for widget in scrollable_frame_1.winfo_children(): widget.destroy()
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        in_constants = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if line.startswith('[') and line.endswith(']'):
                in_constants = (line.lower() == "[constants]")
                continue
            if in_constants and line.startswith("global persist"):
                saved_presets.append(line)
        
        if saved_presets:
            for preset in saved_presets:
                var = tk.BooleanVar(value=True)
                chk = tk.Checkbutton(scrollable_frame_1, text=preset, variable=var, anchor="w", bg="#f0f0f0")
                chk.pack(fill="x", padx=5, pady=2)
                variable_vars[preset] = var
            scrollable_frame_1.update_idletasks()
            canvas_1.config(scrollregion=canvas_1.bbox("all"))
        else:
            tk.Label(scrollable_frame_1, text=L.get("msg_no_persist", "No 'global persist' constants found."), bg="#f0f0f0").pack(pady=10)
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_error_generic", "Error: {}").format(e))

def save_step_preset_1():
    global active_presets_step1, variable_vars
    active_presets_step1.clear()
    
    for preset, var in variable_vars.items():
        if var.get(): active_presets_step1.append(preset)
            
    try:
        with open("step_data.json", "w", encoding="utf-8") as f:
            json.dump(active_presets_step1, f, indent=4, ensure_ascii=False)
        messagebox.showinfo(L.get("msg_success", "Успех"), L.get("msg_vars_saved", "Сохранено {} переменных!").format(len(active_presets_step1)))
        load_variables_from_step_data()
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_error_generic", "Error: {}").format(e))

# ==========================================
# ВКЛАДКА 2
# ==========================================
def log_tab2(message):
    console_2.config(state=tk.NORMAL)
    console_2.insert(tk.END, message + "\n")
    console_2.see(tk.END)
    console_2.config(state=tk.DISABLED)

def init_tab2():
    global active_presets_step2
    lbl_path_2.config(text=L.get("lbl_migoto_path", "3dmigoto Path: {}").format(migoto_path or L.get("not_set", "Not set")))
    try:
        with open("step_data.json", "r", encoding="utf-8") as f:
            active_presets_step2 = json.load(f)
            log_tab2(L.get("log_loaded_vars", "Загружено {} переменных из Шага 1.").format(len(active_presets_step2)))
    except Exception:
        log_tab2(L.get("msg_step_data_missing", "Ошибка: step_data.json не найден."))
        
def detect_namespace(mod_dir):
    """Ищет строку namespace в INI-файлах мода и возвращает её, если находит."""
    if not mod_dir: return None
    for root, _, files in os.walk(mod_dir):
        for file in files:
            if file.endswith('.ini') and not file.startswith('DISABLED_'):
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        for line in f:
                            # Ищем строку вида namespace = XXX или namespace=XXX
                            match = re.search(r'^\s*namespace\s*=\s*(.+?)\s*$', line, re.IGNORECASE)
                            if match:
                                return match.group(1).strip()
                except Exception:
                    continue
    return None
    
def save_step_2():
    global current_step_num, outfit_buffer
    if not migoto_path or not active_presets_step2:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_no_path_or_vars", "Нет пути или переменных."))
        return

    d3dx_file = os.path.join(migoto_path, "d3dx_user.ini")
    if not os.path.exists(d3dx_file):
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_d3dx_not_found", "Файл d3dx_user.ini не найден."))
        return

    # --- НОВАЯ ЛОГИКА ОПРЕДЕЛЕНИЯ ФИЛЬТРА ---
    ignore_paths = var_ignore_paths.get()
    mod_folder_name = os.path.basename(os.path.normpath(mod_path)).lower() if mod_path else ""
    
    # Пытаемся найти namespace
    namespace = detect_namespace(mod_path)
    if namespace:
        log_tab2(L.get("log_namespace_found", "[!] Namespace found: {}. Filtering by it.").format(namespace))
    
    found_values = {}
    with open(d3dx_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for preset_line in active_presets_step2:
        # Надежное извлечение имени переменной (не зависит от пробелов и слова persist)
        var_match = re.search(r'\$([a-zA-Z0-9_]+)', preset_line)
        if not var_match:
            continue
            
        var_name_raw = var_match.group(1)
        
        # 3dmigoto сохраняет переменные в нижнем регистре
        var_name_lower = var_name_raw.lower()
        pattern = re.compile(rf"\\{re.escape(var_name_lower)}\s*=\s*(.+)", re.IGNORECASE)
        
        for line in reversed(lines):
            # Если НЕ стоит галочка "Игнорировать", применяем фильтр
            if not ignore_paths:
                if namespace:
                    # Если есть namespace, ищем его в строке
                    if f"\\{namespace.lower()}\\" not in line.lower():
                        continue
                elif mod_folder_name:
                    # Иначе ищем по имени папки (старая логика)
                    if mod_folder_name not in line.lower():
                        continue
            
            match = pattern.search(line)
            if match:
                found_values[f"${var_name_raw}"] = match.group(1).strip()
                break
                
    if not found_values:
        warning_msg = L.get("msg_namespace_warning", "Не найдены переменные...")
        if not ignore_paths and not namespace:
            warning_msg = L.get("msg_no_vars", "Variables for mod {} not found in d3dx_user.ini.").format(mod_folder_name)
        messagebox.showwarning(L.get("msg_warning", "Внимание"), warning_msg)
        return

    outfit_buffer.append(str(current_step_num))
    for var, val in found_values.items():
        outfit_buffer.append(f"{var} = {val}")
    
    log_tab2(L.get("log_step_saved", "Step {} saved to memory.").format(current_step_num))
    current_step_num += 1
    lbl_status_2.config(text=L.get("status_outfit", "Создан и обрабатывается outfit{}.txt (Шагов: {})").format(current_outfit_num, current_step_num - 1))
    
def finish_outfit():
    global outfit_buffer, current_outfit_num
    if not outfit_buffer:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_no_saved_steps", "Нет сохраненных шагов."))
        return
    if not mod_path:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_mod_path_not_found", "Путь к моду не найден."))
        return

    outfit_file = os.path.join(mod_path, "outfit.txt")
    with open(outfit_file, "w", encoding="utf-8") as f:
        f.write("\n".join(outfit_buffer) + "\n")
        
    log_tab2(L.get("log_outfit_created", "outfit.txt file created..."))

    try:
        sections = parse_sections_2(outfit_file)
        var_dicts = build_variable_dicts_2(sections)
        changed_vars = find_changed_variables_2(var_dicts)

        ref_file = os.path.join(mod_path, "reference.txt")
        with open(ref_file, 'w', encoding='utf-8') as f:
            for var in changed_vars: f.write(var + '\n')
                
        all_vars_count = len(var_dicts[0]) if var_dicts else 0
        changed_count = len(changed_vars)
        
        log_tab2(L.get("log_analysis", "Analysis: found {} variables, {} changing.").format(all_vars_count, changed_count))
        
        if all_vars_count > changed_count:
            ans = messagebox.askyesno(L.get("msg_clean_title", "Очистка"), L.get("msg_clean_text", "Найдены неиспользуемые переменные ({} шт).\nОчистить их?").format(all_vars_count - changed_count))
            if ans:
                allowed = set(changed_vars)
                clean_file = os.path.join(mod_path, f"outfit{current_outfit_num}.txt")
                with open(outfit_file, 'r', encoding='utf-8') as fin, open(clean_file, 'w', encoding='utf-8') as fout:
                    for line in fin:
                        line = line.rstrip('\n')
                        if line.startswith('$'):
                            if line.split()[0] in allowed: fout.write(line + '\n')
                        else: fout.write(line + '\n')
                log_tab2(L.get("log_cleaned_saved", "Cleaned! Saved to outfit{}.txt").format(current_outfit_num))
            else:
                final_file = os.path.join(mod_path, f"outfit{current_outfit_num}.txt")
                shutil.copy(outfit_file, final_file)
                log_tab2(L.get("log_saved_uncleaned", "Saved without cleanup to outfit{}.txt").format(current_outfit_num))
        else:
            final_file = os.path.join(mod_path, f"outfit{current_outfit_num}.txt")
            shutil.copy(outfit_file, final_file)
            log_tab2(L.get("log_saved_to", "Saved to outfit{}.txt").format(current_outfit_num))

        messagebox.showinfo(L.get("msg_success", "Успех"), L.get("msg_outfit_finished", "Костюм outfit{}.txt успешно завершен!").format(current_outfit_num))
        
    except Exception as e:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_error_generic", "Error: {}").format(e))

def next_outfit():
    global current_outfit_num, current_step_num, outfit_buffer
    current_outfit_num += 1
    current_step_num = 1
    outfit_buffer.clear()
    log_tab2(L.get("log_next_outfit", "--- ПЕРЕХОД К НОВОМУ КОСТЮМУ (outfit{}) ---").format(current_outfit_num))
    lbl_status_2.config(text=L.get("status_outfit", "Создан и обрабатывается outfit{}.txt (Шагов: {})").format(current_outfit_num, 0))

def reset_outfit_session():
    global current_outfit_num, current_step_num, outfit_buffer
    current_outfit_num = 1
    current_step_num = 1
    outfit_buffer.clear()
    log_tab2(L.get("log_session_cleared", "--- СЕССИЯ ОЧИЩЕНА. МОЖНО НАЧИНАТЬ НОВЫЙ МОД ---"))
    lbl_status_2.config(text=L.get("status_outfit", "Создан и обрабатывается outfit{}.txt (Шагов: {})").format(current_outfit_num, 0))

def parse_sections_2(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    sections, current_section = [], []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^\d+$', stripped):
            if current_section: sections.append(current_section); current_section = []
        else: current_section.append(line)
    if current_section: sections.append(current_section)
    return sections

def build_variable_dicts_2(sections):
    vars_list = []
    for sec in sections:
        var_dict = {}
        for line in sec:
            stripped = line.strip()
            if stripped.startswith('$') and '=' in stripped:
                var, value = stripped.split('=', 1)
                var_dict[var.strip()] = value.strip()
        vars_list.append(var_dict)
    return vars_list

def find_changed_variables_2(vars_list):
    all_keys = set()
    for d in vars_list: all_keys.update(d.keys())
    changed = []
    for key in all_keys:
        values = [d.get(key) for d in vars_list]
        if any(v != values[0] for v in values): changed.append(key)
    return changed

# ==========================================
# ВКЛАДКА 3
# ==========================================
def log_message_3(message):
    console_3.config(state=tk.NORMAL)
    console_3.insert(tk.END, message + "\n")
    console_3.see(tk.END)
    console_3.config(state=tk.DISABLED)

def auto_detect():
    if not mod_dir_global: return
    entry_name.delete(0, tk.END)
    entry_name.insert(0, L.get("lbl_searching", "Поиск..."))
    root.update()
    detected = health_system.detect_character_name(mod_dir_global)
    entry_name.delete(0, tk.END)
    if detected:
        entry_name.insert(0, detected)
        log_message_3(L.get("log_health_char_found", "[Health] Character found: '{}'").format(detected))
    else:
        log_message_3(L.get("log_health_hash_not_found", "[Health] Hash not found."))

def refresh_health_ini_list():
    """Обновляет список INI файлов для вкладки Здоровья"""
    files = get_ini_files_in_mod()
    combo_health_ini['values'] = files
    # Если файлы есть, всегда выбираем первый, чтобы обновить отображение
    if files:
        combo_health_ini.current(0)
    else:
        combo_health_ini.set('')

def run_health():
    char_name = entry_name.get().strip()
    target_ini = combo_health_ini.get() # <--- Получаем выбранный файл
    
    if not char_name or char_name == L.get("lbl_searching", "Searching..."):
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_enter_char_name", "Введите имя персонажа!"))
        return
        
    if not target_ini:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_select_ini", "Выберите INI файл для обработки!"))
        return
    
    btn_h.config(state=tk.DISABLED, text=L.get("lbl_processing", "Обработка..."))
    def task():
        try:
            log_message_3(L.get("log_health_started", "=== Starting health for '{}' in file {} ===").format(char_name, target_ini))
            health_system.process_ini_file(mod_dir_global, target_ini, char_name, log_message_3, L=L)
        except Exception as e:
            import traceback
            log_message_3(f"[CRITICAL] {e}")
            log_message_3(traceback.format_exc())
        finally:
            btn_h.config(state=tk.NORMAL, text=L.get("apply_health_btn", "ПРИМЕНИТЬ СИСТЕМУ ЗДОРОВЬЯ"))
    threading.Thread(target=task, daemon=True).start()

def refresh_ini_list_merge():
    checkbox_vars.clear()
    for widget in frame_checkboxes_3.winfo_children(): widget.destroy()
    for f in get_ini_files_in_mod():
        var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(frame_checkboxes_3, text=f, variable=var, anchor="w")
        chk.pack(fill="x", padx=5, pady=2)
        checkbox_vars[f] = var
    frame_checkboxes_3.update_idletasks()
    canvas_ini_3.config(scrollregion=canvas_ini_3.bbox("all"))

def run_merge():
    sources = [fname for fname, var in checkbox_vars.items() if var.get()]
    if len(sources) < 2:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_choose_two_files", "Выберите минимум 2 файла."))
        return
    
    out_name = entry_out.get().strip() or os.path.splitext(sources[0])[0] + "_merged.ini"
    if not out_name.endswith('.ini'): out_name += '.ini'
    swapset = "$swapsetmergecostume"
    key = entry_key.get().strip() or "z"
    back = entry_back.get().strip() or "x"

    btn_m.config(state=tk.DISABLED, text=L.get("lbl_merging", "Объединение..."))
    def task():
        try:
            log_message_3(L.get("log_merge_started", "=== Starting merge ==="))
            merger.process_merge(mod_dir_global, sources, out_name, swapset, key, back, log_message_3, L=L)
        except Exception as e:
            import traceback
            log_message_3(f"[CRITICAL] {e}")
            log_message_3(traceback.format_exc())
        finally:
            btn_m.config(state=tk.NORMAL, text=L.get("merge_btn", "ОБЪЕДИНИТЬ ВЫБРАННЫЕ INI"))
    threading.Thread(target=task, daemon=True).start()

def update_selected_path(event=None):
    selected = combo_ini.get()
    lbl_full_path.config(text=L.get("selected_label", "Выбран: {}").format(selected) if selected else "")

def refresh_ini_list_random():
    combo_ini['values'] = get_ini_files_in_mod()
    if combo_ini['values']: combo_ini.current(0)
    update_selected_path()

def load_variables_from_step_data():
    global randomizer_checkbox_vars
    randomizer_checkbox_vars.clear()
    for widget in frame_rand_checkboxes.winfo_children(): widget.destroy()
        
    merge_var = "$swapsetmergecostume"
    var = tk.BooleanVar(value=False)
    chk = tk.Checkbutton(frame_rand_checkboxes, text=merge_var, variable=var, anchor="w", fg="blue")
    chk.pack(fill="x", padx=5, pady=2)
    randomizer_checkbox_vars[merge_var] = var

    if not os.path.exists("step_data.json"):
        tk.Label(frame_rand_checkboxes, text=L.get("msg_step_data_missing", "Файл step_data.json не найден!"), fg="red").pack(pady=10)
        frame_rand_checkboxes.update_idletasks()
        canvas_rand.config(scrollregion=canvas_rand.bbox("all"))
        return

    try:
        with open("step_data.json", "r", encoding="utf-8") as f:
            presets = json.load(f)
            
        for line in presets:
            match = re.search(r'\$([a-zA-Z0-9_]+)', line)
            if match:
                var_name = f"${match.group(1)}"
                if var_name not in randomizer_checkbox_vars: 
                    var = tk.BooleanVar(value=False)
                    chk = tk.Checkbutton(frame_rand_checkboxes, text=var_name, variable=var, anchor="w")
                    chk.pack(fill="x", padx=5, pady=2)
                    randomizer_checkbox_vars[var_name] = var
                    
        frame_rand_checkboxes.update_idletasks()
        canvas_rand.config(scrollregion=canvas_rand.bbox("all"))
    except Exception as e:
        log_message_3(L.get("log_step_data_error", "Error loading step_data.json: {}").format(e))    

def add_random_var():
    selected_vars = [name for name, var in randomizer_checkbox_vars.items() if var.get()]
    if not selected_vars:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_choose_vars", "Выберите переменные галочками."))
        return
    values_str = entry_var_values.get().strip()
    if not values_str:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_enter_values", "Введите значения."))
        return
    try: values = [int(x) for x in values_str.split()]
    except ValueError:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_int_error", "Значения должны быть целыми числами."))
        return

    use_custom = var_custom_interval.get()
    try: base_int = float(entry_base_interval.get())
    except ValueError: base_int = 30.0

    if use_custom:
        try: custom_val = float(entry_custom_interval.get())
        except ValueError:
            messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_invalid_custom_int", "Неверный свой интервал."))
            return
    else:
        custom_val = base_int

    for name in selected_vars:
        if any(v[0] == name for v in added_random_vars):
            log_message_3(L.get("log_var_already_in_list", "Variable {} is already in the list.").format(name))
            continue
            
        if use_custom:
            custom_count = sum(1 for v in added_random_vars if v[2] != "$switch_interval") + 1
            interval_name = f"$switch_interval_{custom_count}"
            timer_name = f"$last_switch_time_{custom_count}"
        else:
            interval_name = "$switch_interval"
            timer_name = "$last_switch_time"

        added_random_vars.append((name, values, interval_name, timer_name, custom_val))
        listbox_random.insert(tk.END, L.get("list_item_format", "{} -> {} (Interval: {})").format(name, values, custom_val if use_custom else L.get("interval_base", "Base")))
        randomizer_checkbox_vars[name].set(False)

    entry_var_values.delete(0, tk.END)
    var_custom_interval.set(False)
    
def clear_random_list():
    global added_random_vars
    added_random_vars.clear()
    listbox_random.delete(0, tk.END)
    log_message_3(L.get("log_randomizer_cleared", "[Randomizer] List cleared."))
    
def run_randomizer():
    if not added_random_vars:
        messagebox.showwarning(L.get("msg_warning", "Внимание"), L.get("msg_list_empty", "Список пуст."))
        return
    target_file = combo_ini.get()
    if not target_file:
        messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_choose_ini", "Выберите INI файл."))
        return
    try: base_int = float(entry_base_interval.get())
    except ValueError: base_int = 30.0

    btn_r.config(state=tk.DISABLED, text=L.get("lbl_applying", "Применение..."))
    def task():
        try:
            log_message_3(L.get("log_randomizer_started", "=== Starting randomizer for {} ===").format(target_file))
            success = randomizer.process_randomizer(mod_dir_global, target_file, base_int, added_random_vars, log_message_3, L=L)
            if success: 
                root.after(0, clear_random_list)
        except Exception as e:
            import traceback
            log_message_3(f"[CRITICAL] {e}")
            log_message_3(traceback.format_exc())
        finally:
            btn_r.config(state=tk.NORMAL, text=L.get("apply_random_btn", "ПРИМЕНИТЬ РАНДОМАЙЗЕР"))
    threading.Thread(target=task, daemon=True).start()

# ==========================================
# СОЗДАНИЕ ОКНА
# ==========================================
# ==========================================
# СОЗДАНИЕ ОКНА
# ==========================================
root = tk.Tk()
root.title(L.get("app_title", "3dmigoto Mod Processor"))

# Безопасная установка иконки
try:
    icon_path = resource_path("myicon.ico")
    if os.path.exists(icon_path):
        # Добавляем default= для принудительной установки
        root.iconbitmap(default=icon_path) 
    else:
        print(f"Файл иконки не найден по пути: {icon_path}")
except Exception as e:
    print(f"Ошибка загрузки иконки: {e}")

root.geometry("850x850")

# --- ПАНЕЛЬ ВЫБОРА ЯЗЫКА ---
frame_lang = tk.Frame(root, bg="#e0e0e0")
frame_lang.pack(fill="x", side=tk.TOP)

tk.Label(frame_lang, text=L.get("language_selector_label", "Language / Язык:"), bg="#e0e0e0", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=10, pady=5)

available_langs = get_available_languages()
lang_names = list(available_langs.keys())

# Находим текущее название языка для отображения в списке
current_lang_name = next((name for name, file in available_langs.items() if file == CURRENT_LANG_FILE), L.get("lang_unknown", "Unknown"))

combo_lang = ttk.Combobox(frame_lang, values=lang_names, state="readonly", width=15)
combo_lang.set(current_lang_name)
combo_lang.pack(side=tk.LEFT, padx=5)

def change_language(event=None):
    selected_name = combo_lang.get()
    if selected_name in available_langs:
        new_file = available_langs[selected_name]
        if new_file != CURRENT_LANG_FILE:
            try:
                # Сохраняем в конфиг
                config = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                config["language_file"] = new_file
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                
                # --- НОВЫЙ БЛОК ПЕРЕЗАПУСКА ЧЕРЕЗ os.execv ---
                # Закрываем текущее окно (чтобы не висело в памяти)
                root.destroy()
                
                # Определяем аргументы для перезапуска
                if getattr(sys, 'frozen', False):
                    # Если запущен .exe
                    args = [sys.executable] + sys.argv[1:]
                else:
                    # Если запущен .py скрипт
                    args = [sys.executable, sys.argv[0]] + sys.argv[1:]
                
                # Заменяем текущий процесс новым
                os.execv(sys.executable, args)
                # ---------------------------------------------
                
            except Exception as e:
                # Если os.execv не сработал, пробуем старый метод как запасной
                try:
                    if getattr(sys, 'frozen', False):
                        cmd = [sys.executable] + sys.argv[1:]
                    else:
                        cmd = [sys.executable, sys.argv[0]] + sys.argv[1:]
                    cwd_path = os.path.dirname(os.path.abspath(sys.argv[0]))
                    subprocess.Popen(cmd, cwd=cwd_path)
                except Exception:
                    pass
                
                messagebox.showerror(L.get("msg_error", "Ошибка"), L.get("msg_lang_save_error", "Failed to save language: {}").format(e))
                
combo_lang.bind("<<ComboboxSelected>>", change_language)
# ---------------------------

main_notebook = ttk.Notebook(root)
main_notebook.pack(fill="both", expand=True, padx=5, pady=5)

load_global_paths()

# --- ВКЛАДКА 1 ---
tab1 = ttk.Frame(main_notebook)
main_notebook.add(tab1, text=L.get("tab1_title", "1. Подготовка"))

frame_path_1 = tk.Frame(tab1); frame_path_1.pack(pady=10, fill="x")
tk.Label(frame_path_1, text=L.get("path_label", "Путь к 3dmigoto:")).pack(side=tk.LEFT, padx=10)
path_entry = tk.Entry(frame_path_1, width=60)
if saved_path := load_config("migoto_path"): path_entry.insert(0, saved_path)
path_entry.pack(side=tk.LEFT, padx=5)
tk.Button(frame_path_1, text=L.get("browse_btn", "Обзор"), command=browse_migoto_folder).pack(side=tk.LEFT)
tk.Button(frame_path_1, text=L.get("save_btn", "Сохранить"), command=save_migoto_path).pack(side=tk.LEFT, padx=5)

frame_import_1 = tk.Frame(tab1); frame_import_1.pack(pady=5, fill="x")
tk.Label(frame_import_1, text=L.get("import_label", "Импорт мода:")).pack(side=tk.LEFT, padx=10)
tk.Button(frame_import_1, text=L.get("from_archive_btn", "Из архива"), command=handle_select_archive).pack(side=tk.LEFT, padx=5)
tk.Button(frame_import_1, text=L.get("from_folder_btn", "Из папки"), command=handle_select_folder).pack(side=tk.LEFT, padx=5)

tk.Label(tab1, text=L.get("scan_label", "Сканирование INI и выбор переменных:"), font=("Arial", 10, "bold")).pack(pady=10)

frame_scan_1 = tk.Frame(tab1); frame_scan_1.pack(fill="x", padx=20)
tk.Button(frame_scan_1, text=L.get("scan_btn", "Сканировать папку"), command=scan_for_ini_file).pack(side=tk.LEFT)
ini_combobox = ttk.Combobox(frame_scan_1, state="readonly", width=60)
ini_combobox.pack(side=tk.LEFT, padx=10)
ini_combobox.bind("<<ComboboxSelected>>", load_selected_ini)

lbl_full_ini_path = tk.Label(tab1, text="", font=("Arial", 9, "italic"), fg="blue", anchor="w")
lbl_full_ini_path.pack(fill="x", padx=20, pady=(5, 5))

frame_scroll_1 = tk.Frame(tab1)
frame_scroll_1.pack(fill="x", padx=20, pady=5)

canvas_1 = tk.Canvas(frame_scroll_1, bg="#f0f0f0", height=250)
scrollbar_1 = ttk.Scrollbar(frame_scroll_1, orient="vertical", command=canvas_1.yview)

scrollable_frame_1 = tk.Frame(canvas_1, bg="#f0f0f0")
scrollable_frame_1.bind("<Configure>", lambda e: canvas_1.configure(scrollregion=canvas_1.bbox("all")))
canvas_1.create_window((0, 0), window=scrollable_frame_1, anchor="nw")
canvas_1.configure(yscrollcommand=scrollbar_1.set)

scrollbar_1.pack(side="right", fill="y")
canvas_1.pack(side="left", fill="both", expand=True)

tk.Button(tab1, text=L.get("save_preset_btn", "Сохранить выбранные переменные"), command=save_step_preset_1, bg="#e1f5fe").pack(pady=10)

# --- ВКЛАДКА 2 ---
tab2 = ttk.Frame(main_notebook)
main_notebook.add(tab2, text=L.get("tab2_title", "2. Генератор костюмов"))

lbl_path_2 = tk.Label(tab2, text=L.get("lbl_loading", "Загрузка..."), font=("Arial", 9)); lbl_path_2.pack(pady=5)
lbl_status_2 = tk.Label(tab2, text=L.get("status_outfit", "Создан и обрабатывается outfit{}.txt (Шагов: {})").format(1, 0), font=("Arial", 12, "bold"), fg="blue")
lbl_status_2.pack(pady=10)

# --- НОВАЯ ГАЛОЧКА ---
var_ignore_paths = tk.BooleanVar(value=False)
chk_ignore = tk.Checkbutton(tab2, text=L.get("ignore_paths_chk", "Игнорировать пути..."), variable=var_ignore_paths, fg="#d32f2f")
chk_ignore.pack(pady=5)
# ---------------------

tk.Button(tab2, text=L.get("save_step_btn", "СОХРАНИТЬ ШАГ"), command=save_step_2, bg="#e1f5fe", font=("Arial", 11)).pack(pady=10, ipadx=20, ipady=5)
tk.Button(tab2, text=L.get("finish_btn", "ГОТОВО"), command=finish_outfit, bg="#c8e6c9", font=("Arial", 11)).pack(pady=10, ipadx=20, ipady=5)

frame_bottom_2 = tk.Frame(tab2); frame_bottom_2.pack(pady=10)
tk.Button(frame_bottom_2, text=L.get("new_outfit_btn", "Создать ЕЩЁ КОСТЮМ"), command=next_outfit).pack(side=tk.LEFT, padx=10)
tk.Button(frame_bottom_2, text=L.get("reset_session_btn", "Очистить сессию (Новый мод)"), command=reset_outfit_session, bg="#ffcdd2").pack(side=tk.LEFT, padx=10)
tk.Button(frame_bottom_2, text=L.get("goto_tab3_btn", "Перейти к обработке >>"), command=lambda: main_notebook.select(2)).pack(side=tk.LEFT, padx=10)

console_2 = tk.Text(tab2, height=12, width=80, state=tk.DISABLED, bg="#f5f5f5")
console_2.pack(pady=10, padx=20)

# --- ВКЛАДКА 3 ---
tab3 = ttk.Frame(main_notebook)
main_notebook.add(tab3, text=L.get("tab3_title", "3. Инструменты обработки"))

lbl_path_3 = tk.Label(tab3, text=L.get("lbl_current_mod", "Текущий мод: {}").format(mod_dir_global or L.get("mod_not_found", "NOT FOUND")), font=("Arial", 9), fg="gray")
lbl_path_3.pack(pady=5)

sub_notebook = ttk.Notebook(tab3)
sub_notebook.pack(fill="both", expand=True, padx=5, pady=5)

# --- 3.1 Здоровье ---
sub_tab1 = ttk.Frame(sub_notebook); sub_notebook.add(sub_tab1, text=L.get("sub_tab1_health", "Система Здоровья"))
frame_char = tk.LabelFrame(sub_tab1, text=L.get("char_label", "Определение персонажа"), padx=10, pady=10)
frame_char.pack(pady=10, fill="x", padx=20)
# --- НОВЫЙ БЛОК ВЫБОРА INI ФАЙЛА ---
frame_target = tk.Frame(frame_char)
frame_target.pack(fill="x", pady=10)
tk.Label(frame_target, text=L.get("select_health_ini", "Выберите INI файл для обработки:")).pack(anchor="w")

frame_combo_health = tk.Frame(frame_target)
frame_combo_health.pack(anchor="w", pady=2)

combo_health_ini = ttk.Combobox(frame_combo_health, state="readonly", width=50)
combo_health_ini.pack(side=tk.LEFT, padx=(0, 5))

# НОВАЯ КНОПКА ОБНОВЛЕНИЯ
tk.Button(frame_combo_health, text=L.get("refresh_btn", "Обновить"), command=refresh_health_ini_list).pack(side=tk.LEFT)
# -----------------------------------
tk.Label(frame_char, text=L.get("char_label", "Имя персонажа:")).pack(anchor="w")
frame_input = tk.Frame(frame_char); frame_input.pack(fill="x", pady=5)
entry_name = tk.Entry(frame_input, width=30, font=("Arial", 11)); entry_name.pack(side=tk.LEFT, padx=(0, 10))
tk.Button(frame_input, text=L.get("detect_hash_btn", "Найти по хэшу"), command=auto_detect, bg="#e1f5fe").pack(side=tk.LEFT)
btn_h = tk.Button(sub_tab1, text=L.get("apply_health_btn", "ПРИМЕНИТЬ СИСТЕМУ ЗДОРОВЬЯ"), command=run_health, bg="#c8e6c9", font=("Arial", 11, "bold"))
btn_h.pack(pady=15, ipadx=20, ipady=5)

# --- 3.2 Объединение ---
sub_tab2 = ttk.Frame(sub_notebook); sub_notebook.add(sub_tab2, text=L.get("sub_tab2_merge", "Объединение Костюмов"))
frame_merge = tk.Frame(sub_tab2); frame_merge.pack(fill="both", expand=True, padx=20, pady=10)
tk.Label(frame_merge, text=L.get("merge_files_label", "Выберите файлы галочками:"), font=("Arial", 10, "bold")).pack(anchor="w")

frame_scroll_ini_3 = tk.Frame(frame_merge)
frame_scroll_ini_3.pack(fill="x", pady=5)

canvas_ini_3 = tk.Canvas(frame_scroll_ini_3, bg="#f0f0f0", height=150)
scrollbar_ini_3 = ttk.Scrollbar(frame_scroll_ini_3, orient="vertical", command=canvas_ini_3.yview)

frame_checkboxes_3 = tk.Frame(canvas_ini_3, bg="#f0f0f0")
frame_checkboxes_3.bind("<Configure>", lambda e: canvas_ini_3.configure(scrollregion=canvas_ini_3.bbox("all")))
canvas_ini_3.create_window((0, 0), window=frame_checkboxes_3, anchor="nw")
canvas_ini_3.configure(yscrollcommand=scrollbar_ini_3.set)

scrollbar_ini_3.pack(side="right", fill="y")
canvas_ini_3.pack(side="left", fill="both", expand=True)

tk.Button(frame_merge, text=L.get("refresh_list_btn", "Обновить список файлов"), command=refresh_ini_list_merge).pack(anchor="w", pady=5)

frame_params = tk.Frame(frame_merge); frame_params.pack(fill="x", pady=10)
tk.Label(frame_params, text=L.get("out_name_label", "Имя выхода:")).grid(row=0, column=0, sticky="w"); entry_out = tk.Entry(frame_params, width=30); entry_out.grid(row=0, column=1)
tk.Label(frame_params, text=L.get("key_fwd_label", "Клавиша вперед:")).grid(row=1, column=0, sticky="w"); entry_key = tk.Entry(frame_params, width=30); entry_key.grid(row=1, column=1)
tk.Label(frame_params, text=L.get("key_back_label", "Клавиша назад:")).grid(row=2, column=0, sticky="w"); entry_back = tk.Entry(frame_params, width=30); entry_back.grid(row=2, column=1)
btn_m = tk.Button(sub_tab2, text=L.get("merge_btn", "ОБЪЕДИНИТЬ ВЫБРАННЫЕ INI"), command=run_merge, bg="#fff9c4", font=("Arial", 11, "bold"))
btn_m.pack(pady=10, ipadx=20, ipady=5)

# --- 3.3 Рандомайзер ---
sub_tab3 = ttk.Frame(sub_notebook); sub_notebook.add(sub_tab3, text=L.get("sub_tab3_random", "Рандомайзер"))
frame_rand = tk.Frame(sub_tab3); frame_rand.pack(fill="both", expand=True, padx=20, pady=10)

frame_top = tk.Frame(frame_rand); frame_top.pack(fill="x", pady=5)
tk.Label(frame_top, text=L.get("target_ini_label", "Целевой INI:")).grid(row=0, column=0, sticky="w")
combo_ini = ttk.Combobox(frame_top, state="readonly", width=50)
combo_ini.grid(row=0, column=1, padx=5)
combo_ini.bind("<<ComboboxSelected>>", update_selected_path)
tk.Button(frame_top, text=L.get("refresh_btn", "Обновить"), command=refresh_ini_list_random).grid(row=0, column=2)

lbl_full_path = tk.Label(frame_rand, text="", font=("Arial", 9, "italic"), fg="blue", anchor="w")
lbl_full_path.pack(fill="x", padx=5, pady=(0, 5))

frame_base_int = tk.Frame(frame_rand); frame_base_int.pack(fill="x", pady=5)
tk.Label(frame_base_int, text=L.get("base_int_label", "Базовый интервал (сек):")).pack(side=tk.LEFT)
entry_base_interval = tk.Entry(frame_base_int, width=10); entry_base_interval.insert(0, "30.0"); entry_base_interval.pack(side=tk.LEFT, padx=5)

frame_rand_list = tk.LabelFrame(frame_rand, text=L.get("select_vars_label", "1. Выберите переменные"), padx=5, pady=5)
frame_rand_list.pack(fill="x", pady=5)

frame_scroll_rand = tk.Frame(frame_rand_list)
frame_scroll_rand.pack(fill="x", pady=5)

canvas_rand = tk.Canvas(frame_scroll_rand, bg="#f0f0f0", height=120)
scrollbar_rand = ttk.Scrollbar(frame_scroll_rand, orient="vertical", command=canvas_rand.yview)

frame_rand_checkboxes = tk.Frame(canvas_rand, bg="#f0f0f0")
frame_rand_checkboxes.bind("<Configure>", lambda e: canvas_rand.configure(scrollregion=canvas_rand.bbox("all")))
canvas_rand.create_window((0, 0), window=frame_rand_checkboxes, anchor="nw")
canvas_rand.configure(yscrollcommand=scrollbar_rand.set)

scrollbar_rand.pack(side="right", fill="y")
canvas_rand.pack(side="left", fill="both", expand=True)

frame_add = tk.LabelFrame(frame_rand, text=L.get("frame_params_label", "2. Parameters"), padx=5, pady=5)
frame_add.pack(fill="x", pady=5)
tk.Label(frame_add, text=L.get("values_label", "Значения (через пробел):")).grid(row=0, column=0, sticky="w")
entry_var_values = tk.Entry(frame_add, width=25); entry_var_values.grid(row=0, column=1, padx=5, pady=5)
var_custom_interval = tk.BooleanVar()
tk.Checkbutton(frame_add, text=L.get("custom_int_label", "Свой интервал:"), variable=var_custom_interval).grid(row=0, column=2, padx=5)
entry_custom_interval = tk.Entry(frame_add, width=10); entry_custom_interval.grid(row=0, column=3)
tk.Button(frame_add, text=L.get("add_btn", "ДОБАВИТЬ ВЫБРАННЫЕ"), command=add_random_var, bg="#e1f5fe").grid(row=1, column=0, columnspan=4, pady=5)

tk.Label(frame_rand, text=L.get("list_apply_label", "3. Список на применение:"), font=("Arial", 9, "bold")).pack(anchor="w")
listbox_random = tk.Listbox(frame_rand, height=4); listbox_random.pack(fill="x", pady=5)

frame_rand_btns = tk.Frame(sub_tab3); frame_rand_btns.pack(pady=10)
btn_r = tk.Button(frame_rand_btns, text=L.get("apply_random_btn", "ПРИМЕНИТЬ РАНДОМАЙЗЕР"), command=run_randomizer, bg="#ffcc80", font=("Arial", 11, "bold"))
btn_r.pack(side=tk.LEFT, ipadx=20, ipady=5, padx=10)
tk.Button(frame_rand_btns, text=L.get("clear_list_btn", "ОЧИСТИТЬ СПИСОК"), command=clear_random_list, bg="#ffcdd2", font=("Arial", 10)).pack(side=tk.LEFT, ipadx=10, ipady=5)

frame_log_3 = tk.LabelFrame(tab3, text=L.get("log_title_tab3", "Лог операций (Шаг 3)")); frame_log_3.pack(fill="both", expand=True, padx=10, pady=10)
console_3 = tk.Text(frame_log_3, height=6, state=tk.DISABLED, bg="#f5f5f5", font=("Consolas", 9))
scrollbar_3 = tk.Scrollbar(frame_log_3, command=console_3.yview)
console_3.config(yscrollcommand=scrollbar_3.set)
console_3.pack(side=tk.LEFT, fill="both", expand=True); scrollbar_3.pack(side=tk.RIGHT, fill="y")

def on_tab_changed(event):
    selected_tab = main_notebook.index(main_notebook.select())
    load_global_paths()
    
    if selected_tab == 1:
        init_tab2()
    elif selected_tab == 2:
        lbl_path_3.config(text=L.get("lbl_current_mod", "Текущий мод: {}").format(mod_dir_global or L.get("mod_not_found", "NOT FOUND")))
        refresh_ini_list_merge()
        refresh_ini_list_random()
        load_variables_from_step_data()

        combo_health_ini['values'] = get_ini_files_in_mod()
        if combo_health_ini['values'] and not combo_health_ini.get():
            combo_health_ini.current(0)
main_notebook.bind("<<NotebookTabChanged>>", on_tab_changed)
root.after(500, lambda: on_tab_changed(None))

root.mainloop()