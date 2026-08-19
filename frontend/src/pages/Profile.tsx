import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ArrowLeft, Upload, File as FileIcon, CheckCircle, AlertCircle } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'

export default function Profile() {
  const { user, getAccessToken, updateDisplayName } = useAuth()
  const [profile, setProfile] = useState<any>(null)
  const [resumes, setResumes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchProfileAndResumes = async () => {
    try {
      const token = await getAccessToken()
      const [profileRes, resumesRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/profiles/me`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/v1/resumes/`, { headers: { Authorization: `Bearer ${token}` } })
      ])
      
      if (profileRes.ok) setProfile(await profileRes.json())
      if (resumesRes.ok) setResumes(await resumesRes.json())
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchProfileAndResumes()
  }, [])

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    
    if (file.type !== 'application/pdf') {
      setError('Please upload a PDF file.')
      return
    }

    setUploading(true)
    setError('')
    setSuccess('')

    try {
      const token = await getAccessToken()
      
      // If no profile exists, create a basic one first
      if (!profile) {
        const createRes = await fetch(`${API_BASE_URL}/api/v1/profiles/`, {
          method: 'POST',
          headers: { 
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ 
            full_name: user?.user_metadata?.full_name || user?.user_metadata?.name || 'Candidate',
            email: user?.email || '' 
          })
        })
        if (!createRes.ok) {
          let detail = "Failed to create base profile"
          try {
            const body = await createRes.json()
            if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
          } catch { /* Keep the fallback message when the response is not JSON. */ }
          throw new Error(detail)
        }
        setProfile(await createRes.clone().json())
      }

      const formData = new FormData()
      formData.append('file', file)

      const uploadRes = await fetch(`${API_BASE_URL}/api/v1/resumes/`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })

      if (!uploadRes.ok) {
        let detail = 'Failed to upload and process resume'
        try {
          const body = await uploadRes.json()
          if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
        } catch { /* Keep the fallback message when the response is not JSON. */ }
        throw new Error(detail)
      }

      setSuccess('Resume uploaded and processed successfully!')
      fetchProfileAndResumes() // Refresh data
    } catch (err: any) {
      setError(err.message || 'An error occurred during upload')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleLevelConfirm = async (level: string) => {
    try {
      const token = await getAccessToken()
      const res = await fetch(`${API_BASE_URL}/api/v1/profiles/me`, {
        method: 'PATCH',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ confirmed_level: level })
      })
      
      if (res.ok) {
        setProfile(await res.json())
        setSuccess('Level confirmed successfully.')
      } else {
        throw new Error("Failed to confirm level")
      }
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleNameSave = async (name: string) => {
    try {
      const token = await getAccessToken()
      await updateDisplayName(name)
      const res = await fetch(`${API_BASE_URL}/api/v1/profiles/me`, { method: 'PATCH', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ full_name: name.trim() }) })
      if (!res.ok) throw new Error('Failed to update profile name')
      setProfile(await res.json())
      setSuccess('Name updated successfully.')
    } catch (err: any) { setError(err.message || 'Failed to update name') }
  }

  if (loading) return <div className="flex justify-center p-20">Loading...</div>

  return (
    <div className="max-w-4xl mx-auto py-10 px-4">
      <div className="mb-6">
        <Link to="/dashboard" className="text-gray-500 hover:text-gray-900 flex items-center space-x-2 w-fit">
          <ArrowLeft size={16} /> <span>Back to Dashboard</span>
        </Link>
      </div>

      <h1 className="text-3xl font-bold text-gray-900 mb-8">Candidate Profile</h1>

      {error && <div className="mb-6 bg-red-50 text-red-700 p-4 rounded-lg flex items-center"><AlertCircle className="mr-2" size={20}/> {error}</div>}
      {success && <div className="mb-6 bg-green-50 text-green-700 p-4 rounded-lg flex items-center"><CheckCircle className="mr-2" size={20}/> {success}</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Upload Section */}
        <div className="bg-white p-6 rounded-xl border shadow-sm">
          <h2 className="text-xl font-semibold mb-4">Resume</h2>
          
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center bg-gray-50 mb-6">
            <Upload className="mx-auto text-gray-400 mb-2" size={32} />
            <p className="text-sm text-gray-600 mb-4">Upload your PDF resume to automatically fill your profile</p>
            <input 
              type="file" 
              accept=".pdf" 
              className="hidden" 
              ref={fileInputRef}
              onChange={handleFileUpload}
            />
            <button 
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="bg-blue-600 text-white px-4 py-2 rounded shadow-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {uploading ? 'Processing...' : 'Upload PDF'}
            </button>
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-700 uppercase tracking-wide">Uploaded Resumes</h3>
            {resumes.length === 0 ? (
              <p className="text-sm text-gray-500">No resumes uploaded yet.</p>
            ) : (
              resumes.map(r => (
                <div key={r.id} className="flex items-center p-3 bg-gray-50 rounded border justify-between">
                  <div className="flex items-center space-x-3">
                    <FileIcon className="text-red-500" size={20} />
                    <div className="text-sm">
                      <p className="font-medium truncate max-w-[150px]">{r.original_filename}</p>
                      <p className="text-xs text-gray-500">{new Date(r.created_at).toLocaleDateString()}</p>
                    </div>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full ${r.extraction_status === 'COMPLETED' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
                    {r.extraction_status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Profile Data Section */}
        <div className="bg-white p-6 rounded-xl border shadow-sm space-y-6">
          <h2 className="text-xl font-semibold">Extracted Information</h2>
          
          {!profile ? (
            <p className="text-gray-500 text-sm">Upload a resume to generate your profile.</p>
          ) : (
            <>
              <div>
                <p className="text-sm text-gray-500">Name</p>
                <div className="flex gap-2">
                  <input defaultValue={profile.full_name} aria-label="Full name" className="min-w-0 flex-1 rounded border px-2 py-1 text-sm" onKeyDown={(event) => { if (event.key === 'Enter') handleNameSave(event.currentTarget.value) }} />
                  <button type="button" className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700" onClick={(event) => handleNameSave(event.currentTarget.previousElementSibling instanceof HTMLInputElement ? event.currentTarget.previousElementSibling.value : profile.full_name)}>Save</button>
                </div>
              </div>
              
              <div>
                <p className="text-sm text-gray-500">Years of Experience</p>
                <p className="font-medium">{profile.years_of_experience || 0}</p>
              </div>

              <div>
                <p className="text-sm text-gray-500 mb-2">Recommended Level</p>
                <div className="flex items-center justify-between p-3 bg-blue-50 border border-blue-100 rounded-lg">
                  <span className="font-semibold text-blue-800 capitalize">{profile.recommended_level || 'Pending'}</span>
                  {!profile.confirmed_level && profile.recommended_level && (
                    <button 
                      onClick={() => handleLevelConfirm(profile.recommended_level)}
                      className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
                    >
                      Confirm
                    </button>
                  )}
                </div>
              </div>

              <div>
                <p className="text-sm text-gray-500 mb-2">Confirmed Level</p>
                <select 
                  value={profile.confirmed_level || ''} 
                  onChange={(e) => handleLevelConfirm(e.target.value)}
                  className="w-full p-2 border rounded-lg focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="" disabled>Select your level...</option>
                  <option value="junior">Junior</option>
                  <option value="mid">Mid-Level</option>
                  <option value="senior">Senior</option>
                </select>
              </div>

              {profile.skills && profile.skills.length > 0 && (
                <div>
                  <p className="text-sm text-gray-500 mb-2">Skills</p>
                  <div className="flex flex-wrap gap-2">
                    {profile.skills.slice(0, 10).map((skill: string, i: number) => (
                      <span key={i} className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-700">{skill}</span>
                    ))}
                    {profile.skills.length > 10 && <span className="text-xs bg-gray-50 px-2 py-1 rounded text-gray-400">+{profile.skills.length - 10} more</span>}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
