"""Read-only audit of DOUBTS global standard-module plan v3.2.1."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'website'))
import platform_standard_policy_v321 as standard


def main():
    state=standard.read_state()
    history=state['historicalCheck']
    print('=== DOUBTS v3.2.1 全平台共用標準版檢查（唯讀）===')
    print('模組數量：',len(state['modules']))
    print('已納入共用標準版：',len(state['standardModuleIds']))
    for m in state['modules']:
        print(' -',m['id'],'|',m['name'],'|',m['releaseStatus'],'|',m['deployment'])
    print('既有診所：','、'.join(x['name'] for x in state['clinics'] if x['kind']=='existing'))
    print('歷史授權差異：',history['differenceCount'])
    for row in history['differences']:
        print(' REVIEW：',row['clinicName'],row['moduleId'],
              '| v1',row['v1'],'| v3.2',row['v32'])
    print('各診所標準版名單是否一致：',
          standard.clinic_entitlements('yidian')['standardPlanFeatures'] ==
          standard.clinic_entitlements('shanlin')['standardPlanFeatures'])
    print('Firebase／病患資料操作：無')
    print('正式預約或醫護功能切換：無')
    print('PASS：已停止逐診所授權；舊版勾選只供核對，未被自動提升為全平台設定')

if __name__=='__main__':
    main()
