// types/api.ts
export interface SearchResult {
  frame: string;
  distance: number;
  url: string;
  name: string;
}

export interface SearchResponse {
  total_results: number;
  returned_results: number;
  results: SearchResult[];
  query_type: "text" | "image";
  processing_time: number;
  max_distance: number;
}

export interface TextSearchRequest {
  query: string;
  limit?: number;
  rank: number;
  uniqueKeyword: string;
}

export interface ApiError {
  detail: string;
}

export interface ResultSubmit {
  values: number[];
  result: SearchResult;
  answer: string;
  src: string;
}

export interface SubmitRespond {
  code: string;
  message: string;
}

// services/videoSearchApi.ts
const API_BASE_URL = "http://localhost:8000";
class VideoSearchApi {
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(
        error.detail || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }
  async searchByText(
    query: string,
    limit: number = 10,
    rank: number = 3,
    unique_keyword: string
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/text-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit,
        rank,
        unique_keyword,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }

  async searchByTextNoAgent(
    query: string,
    limit: number = 10,
    rank: number = 3,
    unique_keyword: string
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/text-no-agent-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit,
        rank,
        unique_keyword,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }

  async searchByFaiss(
    query: string,
    limit: number = 10,
    rank: number = 3,
    unique_keyword: string
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/faiss-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit,
        rank,
        unique_keyword,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }
  async searchByOCR(
    query: string,
    limit: number = 10,
    rank: number = 3,
    unique_keyword: string
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/ocr-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit,
        rank,
        unique_keyword,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }
  async searchByCombined(
    query: string,
    limit: number = 10,
    rank: number = 3,
    unique_keyword: string
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/combined-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        limit,
        rank,
        unique_keyword,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }
  async filterSearch(
    object: string,
    action: string,
    color: string,
    ocr: string,
    limit: number = 30
  ): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/filter-search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        object,
        action,
        color,
        ocr,
        limit,
      }),
    });

    return this.handleResponse<SearchResponse>(response);
  }

  async searchByImage(
    imageFile: File,
    limit: number = 10
  ): Promise<SearchResponse> {
    const formData = new FormData();
    formData.append("image", imageFile);
    formData.append("limit", limit.toString());

    const response = await fetch(`${API_BASE_URL}/search/image`, {
      method: "POST",
      body: formData,
    });

    return this.handleResponse<SearchResponse>(response);
  }

  async getStatus() {
    const response = await fetch(`${API_BASE_URL}/status`);
    return this.handleResponse(response);
  }
}

class ResultSubmitApi {
  private async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(
        error.detail || `HTTP ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }

  async submit(
    values: number[],
    result: SearchResult,
    answer: string,
    src: string
  ): Promise<SubmitRespond> {
    const dataFinal = {
      values: values,
      result: result,
      answer: answer,
      src: src,
    };

    const response = await fetch(`${API_BASE_URL}/submit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(dataFinal),
    });

    return this.handleResponse<SubmitRespond>(response);
  }
}

export const resultSubmitApi = new ResultSubmitApi();
export const videoSearchApi = new VideoSearchApi();
