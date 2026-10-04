export type WorkshopIdentity<D> = {
    id: string;
    draft: D | null;
    request: number;
    loading: boolean;
};

export type WorkshopIdentityAction<D> =
    | {type: 'select'; id: string; draft: D | null; request: number}
    | {type: 'load'; id: string; request: number}
    | {type: 'loaded'; id: string; draft: D; request: number}
    | {type: 'failed'; id: string; request: number}
    | {type: 'update'; id: string; update: (draft: D | null) => D | null};

export function initialWorkshopIdentity<D>(id: string): WorkshopIdentity<D> {
    return {id, draft: null, request: 0, loading: false};
}

function checkedDraft<D extends {id: string}>(id: string, draft: D | null): D | null {
    if (draft && String(draft.id) !== String(id))
        throw new Error('Workspace identity mismatch: draft.id !== workspace id');
    return draft;
}

// Identity and its visible draft change together. Late responses from a
// previous workspace or author/player view cannot overwrite the current one.
export function workshopIdentityReducer<D extends {id: string}>(
    state: WorkshopIdentity<D>, action: WorkshopIdentityAction<D>,
): WorkshopIdentity<D> {
    if (action.type === 'select')
        return {id: action.id, draft: checkedDraft(action.id, action.draft), request: action.request, loading: false};
    if (action.id !== state.id) return state;
    if (action.type === 'update')
        return {...state, draft: checkedDraft(state.id, action.update(state.draft))};
    if (action.type === 'load')
        return action.request > state.request ? {...state, request: action.request, loading: true} : state;
    if (action.request !== state.request) return state;
    if (action.type === 'loaded')
        return {...state, draft: checkedDraft(state.id, action.draft), loading: false};
    return {...state, loading: false};
}
