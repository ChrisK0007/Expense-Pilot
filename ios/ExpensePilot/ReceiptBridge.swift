import Foundation

/// Camera access uses only the loaded workspace. Uploads always recheck the server.
enum ReceiptBridge {
    static let scanContext = """
    const session = typeof S === 'object' && S ? S : null;
    const user = session && session.user;
    if (!user || session.mfa_required || user.must_change_password) {
        return {ok:false,error:'Connect and sign in, including two-factor authentication and any password change, before scanning. Once your workspace is loaded, you can scan without a connection.'};
    }
    if (!Number.isSafeInteger(user.id) || user.id <= 0 ||
        !(user.role === 'owner' || (user.role === 'tax_agent' && user.permission === 'read_write'))) {
        return {ok:false,error:'This account does not have permission to add receipts.'};
    }
    return {ok:true,userID:user.id};
    """

    static let uploadScan = """
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);
    try {
        const sessionResponse = await fetch('/api/session', {cache:'no-store',redirect:'error',signal:controller.signal});
        if (!sessionResponse.ok) return {ok:false,error:'Cannot check your session. Reconnect, sign in and retry. Your scan is still available while the app stays open.'};
        const session = await sessionResponse.json();
        const user = session.user;
        if (!user || session.mfa_required || user.id !== expectedUser) {
            return {ok:false,error:'Sign in to the account that scanned this receipt, complete two-factor authentication, then retry. Your scan has not been discarded.'};
        }
        if (user.must_change_password) return {ok:false,error:'Change your temporary password, then retry.'};
        if (!(user.role === 'owner' || (user.role === 'tax_agent' && user.permission === 'read_write'))) {
            return {ok:false,error:'This account no longer has permission to add receipts. Your scan has not been discarded.'};
        }
        const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
        const form = new FormData();
        form.append('file',new Blob([bytes],{type:'application/pdf'}),filename);
        const response = await fetch('/api/receipts', {method:'POST',headers:{'X-CSRF-Token':session.csrf},body:form,redirect:'error',signal:controller.signal});
        const result = await response.json();
        if (!response.ok) return {ok:false,error:result.error || 'Upload failed. Reconnect and retry. Your scan has not been discarded.'};
        // A rendering error must not turn a confirmed upload into a failed upload.
        try {
            if (typeof render === 'function' && typeof page !== 'undefined') { page='receipts'; render(); }
        } catch (_) {}
        return {ok:true,duplicate:!!result.duplicate};
    } catch (_) {
        return {ok:false,error:'Cannot reach your server. Your scan is waiting to upload. Keep the app open, reconnect, then tap Retry upload.'};
    } finally {
        clearTimeout(timeout);
    }
    """
}
