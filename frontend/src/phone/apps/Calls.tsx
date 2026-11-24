import { formatDateLabel } from '../../gameDate';
import { useDevice } from '../usePhone';

export function Calls(){
  const {avatar, phone, save, status}=useDevice();
  return (<>
      <p className="phone-section-label">История звонков</p>
      {!phone.events.some(e=>e.channel==='VOICE_CALL')&&<p>Звонков пока нет. Выбери контакт, чтобы позвонить.</p>}
      {phone.events
        .filter((e) => e.channel === "VOICE_CALL")
        .slice()
        .reverse()
        .map((e) => (
          <article className={`phone-row phone-call-row ${e.status==='missed'?'is-missed':''}`} key={e.id}>
            {avatar(e.subject)}
            <div>
              <strong>{e.label}</strong>
              {(e.status==='answered'||(e.status==='ended'&&save.turns.some(turn=>turn.presentation?.call_id===e.id&&turn.assistant_text.trim())))&&<button onClick={()=>{window.dispatchEvent(new CustomEvent('phone-call-open',{detail:e.id}))}}>Читать разговор</button>}
              <small>
                {e.outgoing ? "Исходящий" : "Входящий"} ·{" "}
                {status[e.status]} · {formatDateLabel(e.time_label)}
              </small>
            </div>
          </article>
        ))}
    </>);
}
