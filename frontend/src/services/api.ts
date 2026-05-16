import axios from 'axios';
import { GenerateResponse, StatusResponse, ResultResponse, QuizMode } from '../types';

const API_URL = 'http://localhost:8000';

export const api = {
  async generateQuiz(file: File, mode: QuizMode, numQuestions: number): Promise<GenerateResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mode', mode);
    formData.append('num_questions', numQuestions.toString());

    // Assuming the backend field might be 'pdf' instead of 'file', let's use 'file' as per the prompt first, but wait, the prompt says "FormData: pdf file, mode, num_questions"
    // Let's use 'file' but maybe we should check. I'll use 'file' because usually FastAPI UploadFile is named file.
  
    const formData2 = new FormData();
    formData2.append('pdf', file);
    formData2.append('mode', mode);
    formData2.append('num_questions', numQuestions.toString());

    // Just send pdf since prompt says "pdf file"
    const response = await axios.post<GenerateResponse>(`${API_URL}/generate`, formData2, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async getStatus(jobId: string): Promise<StatusResponse> {
    const response = await axios.get<StatusResponse>(`${API_URL}/status/${jobId}`);
    return response.data;
  },

  async getResult(jobId: string): Promise<ResultResponse> {
    const response = await axios.get<ResultResponse>(`${API_URL}/result/${jobId}`);
    return response.data;
  }
};
